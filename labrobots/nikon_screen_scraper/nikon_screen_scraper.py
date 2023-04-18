import PIL
import pytesseract
from PIL import Image, ImageGrab, ImageOps, ImageEnhance, ImageChops, ImageFilter
import numpy as np
import sqlite3
from typing import *
import re
from pprint import pprint
import json

from scipy.signal import convolve2d
import datetime

import sys

def take_screenshot():
    return ImageGrab.grab(None, all_screens=True)

def vcat(image1, image2):
    w1, h1 = image1.size
    w2, h2 = image2.size
    new_image = Image.new(image1.mode, (max(w1, w2), h1 + h2))
    new_image.paste(image1, (0, 0))
    new_image.paste(image2, (0, h1))
    return new_image

def double_image_size(image):
    w, h = image.size
    return image.resize((w * 2, h * 2))

white = (255, 255, 255)
black = (0, 0, 0)
nikon_blue_1 = (58, 119, 200)
nikon_blue_2 = (61, 118, 199)
nikon_blue_3 = (59, 120, 200)

def read_progress_text(img: Image) -> 'tuple[Union[Image, None], dict[str, str]]':
    xs = np.asarray(img)
    mask = (
        # something wrong with the color space modes, I don't know exactly what RGB values the blue has from ImageGrab
        ((xs[:, :, 0] == nikon_blue_3[0]) | (xs[:, :, 0] == nikon_blue_1[0]) | (xs[:, :, 0] == nikon_blue_2[0])) &
        ((xs[:, :, 1] == nikon_blue_3[1]) | (xs[:, :, 1] == nikon_blue_1[1]) | (xs[:, :, 1] == nikon_blue_2[1])) &
        ((xs[:, :, 2] == nikon_blue_3[2]) | (xs[:, :, 2] == nikon_blue_1[2]) | (xs[:, :, 2] == nikon_blue_2[2]))
    )
    mask = 1 * mask.astype(np.uint8)
    print('mask', 'shape:', mask.shape, 'sum:', mask.sum(), 'max:', mask.max())

    # create a kernel of the desired patch size
    patch_size = (41, 41)
    kernel = np.ones(patch_size)

    # perform the convolution operation
    result = convolve2d(mask, kernel, mode='valid')
    print('result', 'shape:', result.shape, 'sum:', result.sum(), 'max:', result.max())
    mask = (result == np.prod(patch_size))
    mask = 255 * mask.astype(np.uint8)
    mask = Image.fromarray(mask, mode='L')
    print('bbox:', mask.getbbox())
    if mask.getbbox() is None:
        return None, {}
    (x0, y0, x1, y1) = mask.getbbox()
    bbox = (x0, y0, x1 + patch_size[0] - 1, y1 + patch_size[1] - 1)
    mask.crop(bbox).save('mask.png')
    img = img.convert('L')
    img = img.crop(bbox)
    img = img.point(lambda c: 256 - max(0, 2 * (c - 128)))
    img_LU = double_image_size(img.crop((0, 0, img.width // 2, img.height // 4 * 3)))
    img_R = img.crop((img.width // 2, 0, img.width, img.height))
    text: str = (
        pytesseract.image_to_string(img_LU, config='--psm 6') #  --psm 6: Single uniform block of text
        +
        pytesseract.image_to_string(img_R, config='--psm 7')  #  --psm 7: Treat the image as a single text line
    )
    text = text.replace('well', 'Well')
    text = text.replace('points', 'Points')
                 #Well(2, 2): A2
    res: dict[str, str] = {}
    for line in text.splitlines():
        match re.findall('[\w\d][\w\d:/]*', line):
            case ['Well', i, N, name]:
                res['well'] = f'{name} ({i}/{N})'
            case ['Points', i, N]:
                res['point'] = f'{i}/{N}'
            case ['Time', 'remaining:', hhmmss]:
                res['countdown'] = hhmmss
            case xs:
                print(xs)
    res['lines'] = text
    return vcat(img_LU, img_R), res

def main():
    if len(sys.argv) <= 1 or sys.argv[1] == 'screenshot':
        img = take_screenshot()
        # save and reload to compensate for color space mismatches
        img.save('screenshot.png')
        img = Image.open('screenshot.png')
    else:
        img = Image.open(sys.argv[1])

    img, data = read_progress_text(img)
    if img:
        img.save('screenshot-crop.png')

    pprint(data, sort_dicts=False)

    c = sqlite3.connect('ocr.db', isolation_level=None)
    c.executescript('''
        pragma WAL=true;
        pragma busy_timeout=1000;
        create table if not exists ocr (
            t     timestamp default (strftime('%Y-%m-%d %H:%M:%f', 'now', 'localtime')),
            data  json
        );
    ''')
    c.execute('insert into ocr(data) values (?);', (json.dumps(data),))
    c.close()

if __name__ == '__main__':
    main()

