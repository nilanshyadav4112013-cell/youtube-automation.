import os, csv, json, asyncio, datetime, textwrap
import anthropic
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

W, H = 1080, 1920
VOICE = "en-IN-NeerjaNeural"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def pick_topic():
    with open("topics.csv", encoding="utf-8") as f:
        topics = [r[0] for r in csv.reader(f) if r]
    return topics[datetime.date.today().toordinal() % len(topics)]


def make_script(topic):
    client = anthropic.Anthropic()
    prompt = f"""Write a 45-second YouTube Shorts script about: {topic}.
Audience: beginners in India. Educational only, no guaranteed-return claims.
Return ONLY JSON like:
{{"title": "...", "description": "...", "lines": ["line 1", "line 2"]}}
Use 6 to 8 short lines. First line is a hook. Last line asks viewers to follow."""
    msg = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


async def tts(text, path):
    await edge_tts.Communicate(text, VOICE).save(path)


def make_frame(text, path):
    img = Image.new("RGB", (W, H), (18, 32, 64))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 80)
    lines = textwrap.wrap(text, 22)
    y = H // 2 - len(lines) * 55
    for ln in lines:
        w = d.textlength(ln, font=font)
        d.text(((W - w) / 2, y), ln, font=font, fill="white")
        y += 110
    img.save(path)


def build_video(lines):
    clips = []
    for i, line in enumerate(lines):
        mp3, png = f"/tmp/l{i}.mp3", f"/tmp/l{i}.png"
        asyncio.run(tts(line, mp3))
        make_frame(line, png)
        audio = AudioFileClip(mp3)
        clip = ImageClip(png).set_duration(audio.duration + 0.3).set_audio(audio)
        clips.append(clip)
    video = concatenate_videoclips(clips, method="compose")
    video.write_videofile("out.mp4", fps=24, codec="libx264", audio_codec="aac")


def upload(data):
    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    yt = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": data["title"][:90] + " #Shorts",
            "description": data["description"]
            + "\n\nEducational content only, not financial advice.",
            "categoryId": "27",
        },
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False},
    }
    req = yt.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload("out.mp4", resumable=True),
    )
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    print("Uploaded:", resp["id"])


if __name__ == "__main__":
    topic = pick_topic()
    data = make_script(topic)
    build_video(data["lines"])
    upload(data)
