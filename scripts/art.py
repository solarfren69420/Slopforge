"""Generate original, symbolic SVG card art. These are not game screenshots."""
import math
import random
from pathlib import Path


def make_art(project):
    rng = random.Random(project['id'])
    hue = project['hue'] % 360
    color = f'hsl({hue},85%,65%)'
    light = f'hsl({(hue + 45) % 360},80%,75%)'
    shapes = []
    for _ in range(45):
        x, y = rng.randint(0, 600), rng.randint(0, 300)
        shapes.append(f'<circle cx="{x}" cy="{y}" r="{rng.choice([.6,1,1.5])}" fill="{light}" opacity="{rng.uniform(.1,.5):.2f}"/>')
    theme = project['art']
    if theme in ('landscape', 'adventure', 'platformer', 'dungeon'):
        shapes.append(f'<circle cx="455" cy="82" r="47" fill="{color}" opacity=".15"/><circle cx="455" cy="82" r="35" fill="{light}" opacity=".5"/>')
        for n in range(3):
            points = [(0, 300)] + [(x, rng.randint(120+n*35, 175+n*35)) for x in range(0, 650, 60)] + [(600, 300)]
            shapes.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in points)}" fill="hsl({hue},{45-n*8}%,{28-n*6}%)"/>')
        shapes.append(f'<path d="M350 200v-80l25-25 25 25v80m-45-80h40m-20-25V70m-20 105h40" fill="#11182d" stroke="{light}" stroke-width="2"/>')
    elif theme in ('city','park','strategy'):
        shapes.append(f'<path d="M0 260 600 140M0 300 600 180M80 300 600 215M0 180 450 300M0 140 570 300" stroke="{color}" opacity=".2"/>')
        for x in range(160, 580, 45):
            y, h = rng.randint(125, 215), rng.randint(35, 120)
            shapes.append(f'<path d="M{x} {y}v-{h}l25-12 20 12v{h}l-20 13z" fill="#151d38" stroke="{color}" stroke-opacity=".7"/><path d="M{x+25} {y-h-12}v{h+25}" stroke="{light}" opacity=".6"/>')
        if theme == 'park':
            shapes.append(f'<circle cx="430" cy="120" r="68" fill="#131a3388" stroke="{light}" stroke-width="4"/><path d="m400 230 30-110 30 110M360 120h140m-70-70v140m-50-120 100 100m-100 0 100-100" stroke="{color}" stroke-width="2" fill="none"/>')
    elif theme in ('space','racing'):
        shapes.append(f'<ellipse cx="430" cy="95" rx="68" ry="68" fill="url(#orb)"/><ellipse cx="430" cy="95" rx="115" ry="23" transform="rotate(-23 430 95)" fill="none" stroke="{light}" stroke-width="3" opacity=".55"/>')
        shapes.append(f'<path d="M100 300 415 145 325 300M0 260 410 140M110 285 410 140M220 300 410 140" fill="#171c3c" stroke="{color}" stroke-width="3" opacity=".7"/>')
        if theme == 'racing':
            shapes.append(f'<path d="m280 215 35-28h85l40 22 5 35H275z" fill="{color}" stroke="{light}" stroke-width="3"/><path d="m327 191-14 21h88l-15-21z" fill="#101730"/><circle cx="303" cy="241" r="14" fill="#0a0e19" stroke="{light}" stroke-width="3"/><circle cx="420" cy="241" r="14" fill="#0a0e19" stroke="{light}" stroke-width="3"/>')
    elif theme in ('three','cad','voxel'):
        for i in range(6):
            x,y,s = rng.randint(240,510),rng.randint(40,190),rng.randint(25,50)
            shapes.append(f'<path d="M{x} {y}l{s} -{s//2} {s} {s//2}v{s}l-{s} {s//2}-{s}-{s//2}z" fill="{color}" fill-opacity=".1" stroke="{light}" stroke-width="2"/><path d="m{x} {y} {s} {s//2} {s}-{s//2}m-{s} {s//2}v{s}" fill="none" stroke="{color}" stroke-width="2"/>')
        shapes.append(f'<path d="M0 300 300 180 600 300M100 300 300 220 500 300M300 180v120" stroke="{color}" opacity=".25" fill="none"/>')
    elif theme == 'audio':
        for i in range(42):
            h = rng.randint(12,160)
            shapes.append(f'<rect x="{190+i*9}" y="{150-h/2}" width="4" height="{h}" rx="2" fill="{light}" opacity="{.4+(i%3)*.2}"/>')
        shapes.append(f'<path d="M160 150h420" stroke="{color}" opacity=".7"/>')
    elif theme in ('circuit','map','code','compat','office','video'):
        for n in range(5):
            y=55+n*38
            shapes.append(f'<path d="M220 {y}h{70+n*20}l35 25h150" fill="none" stroke="{light}" stroke-width="2" opacity=".5"/><circle cx="220" cy="{y}" r="4" fill="{color}"/>')
        if theme in ('office','video','code'):
            shapes.append(f'<rect x="300" y="45" width="235" height="166" rx="9" fill="#0d142d" stroke="{color}" stroke-width="3"/><path d="M300 70h235" stroke="{light}" opacity=".6"/>')
            for i in range(5):
                shapes.append(f'<rect x="320" y="{85+i*23}" width="{rng.randint(50,180)}" height="5" rx="2" fill="{light}" opacity=".5"/>')
            if theme=='video': shapes.append(f'<path d="m385 93 65 40-65 40z" fill="{color}"/>')
    else:
        shapes.append(f'<circle cx="435" cy="140" r="75" fill="{color}" opacity=".13" stroke="{light}" stroke-width="2"/><path d="m310 200 85-135 75 135z" fill="{color}" opacity=".3" stroke="{light}" stroke-width="2"/><rect x="350" y="70" width="130" height="130" rx="14" transform="rotate(30 415 135)" fill="none" stroke="{light}" stroke-width="3"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 300"><defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="hsl({hue},55%,15%)"/><stop offset="1" stop-color="#0a1021"/></linearGradient><radialGradient id="orb"><stop stop-color="{light}"/><stop offset="1" stop-color="hsl({hue},65%,25%)"/></radialGradient><radialGradient id="glow"><stop stop-color="{color}" stop-opacity=".3"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient></defs><rect width="600" height="300" fill="url(#bg)"/><ellipse cx="430" cy="100" rx="230" ry="180" fill="url(#glow)"/>{''.join(shapes)}<path d="M0 295H600" stroke="{light}" stroke-opacity=".3"/></svg>'''


def generate(projects, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for project in projects:
        (output / (project['id'] + '.svg')).write_text(make_art(project), encoding='utf-8')
