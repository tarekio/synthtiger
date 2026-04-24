"""
SynthTIGER
Copyright (c) 2021-present NAVER Corp.
MIT license
"""

import os

import cv2
import numpy as np
from PIL import Image

from synthtiger import components, layers, templates, utils

DEBUG = False

BLEND_MODES = [
    "normal",
    "multiply",
    # "screen",
    # "overlay",
    "hard_light",
    # "soft_light",
    # "dodge",
    # "divide",
    "addition",
    # "difference",
    "darken_only",
    # "lighten_only",
]


def bbox_to_polygon(bbox):
    rel_x, rel_y, fit_w, fit_h = bbox[0], bbox[1], bbox[2], bbox[3]
    return [
        (rel_x, rel_y),
        (rel_x + fit_w, rel_y),
        (rel_x + fit_w, rel_y + fit_h),
        (rel_x, rel_y + fit_h),
    ]


def augment_text(text):
    """
    Augment the input text by applying random choice of Arabic diacritics
    """
    diacritics = ["ً", "ٌ", "ٍ", "َ", "ُ", "ِ", "ّ", "ْ", "ٕ", "ٓ", "ٔ", "ٚ"]

    # check if the text already has diacritics
    existing_diacritics = [char for char in text if char in diacritics]
    if existing_diacritics:
        return text  # skip augmentation if diacritics already exist
    
    # Randomly decide how many diacritics to add (0 to half the length of the text)
    num_diacritics = np.random.randint(0, len(text) // 2 + 1)

    text_chars = list(text)
    for _ in range(num_diacritics - 1):
        # Randomly select a position in the text to add a diacritic
        pos = np.random.randint(0, len(text_chars))
        diacritic = np.random.choice(diacritics)
        text_chars.insert(pos, diacritic)
    # Add the final diacritic at the end of the text
    text_chars.append(np.random.choice(diacritics))
    return "".join(text_chars)


class Detect(templates.Template):
    def __init__(self, config=None):
        if config is None:
            config = {}

        self.counts = config.get("counts", [10, 25])

        self.coord_output = config.get("coord_output", True)

        self.vertical = config.get("vertical", False)
        self.quality = config.get("quality", [95, 95])
        self.visibility_check = config.get("visibility_check", False)

        # self.corpus = components.Selector(
        #     [
        #         components.LengthAugmentableCorpus(),
        #         components.CharAugmentableCorpus(),
        #     ],
        #     **config.get("corpus", {}),
        # )
        self.corpus = components.BaseCorpus(**config.get("corpus", {}))
        self.font = components.BaseFont(**config.get("font", {}))
        self.texture = components.Switch(
            components.BaseTexture(), **config.get("texture", {})
        )
        # self.colormap2 = components.GrayMap(**config.get("colormap2", {}))
        # self.colormap3 = components.GrayMap(**config.get("colormap3", {}))
        self.color = components.Gray(**config.get("color", {}))
        # self.color = components.RGB(**config.get("color", {}))
        self.shape = components.Switch(
            components.Selector(
                [components.ElasticDistortion(), components.ElasticDistortion()]
            ),
            **config.get("shape", {}),
        )
        # self.layout = components.Selector(
        #     [components.TightFlowLayout(), components.CurveLayout()],
        #     **config.get("layout", {}),
        # )
        self.layout = components.TightFlowLayout(**config.get("layout", {}))
        self.style = components.Switch(
            components.Selector(
                [
                    components.TextBorder(),
                    components.TextShadow(),
                    components.TextExtrusion(),
                ]
            ),
            **config.get("style", {}),
        )
        # self.transform = components.Switch(
        #     components.Selector(
        #         [
        #             components.Perspective(),
        #             components.Perspective(),
        #             components.Trapezoidate(),
        #             components.Trapezoidate(),
        #             components.Skew(),
        #             components.Skew(),
        #             components.Rotate(),
        #         ]
        #     ),
        #     **config.get("transform", {}),
        # )
        self.fit = components.Fit()
        self.pad = components.Switch(components.Pad(), **config.get("pad", {}))
        self.postprocess = components.Iterator(
            [
                components.Switch(components.AdditiveGaussianNoise()),
                components.Switch(components.GaussianBlur()),
                components.Switch(components.Resample()),
                components.Switch(components.MedianBlur()),
            ],
            **config.get("postprocess", {}),
        )

    def generate(self, key=None):

        quality = np.random.randint(self.quality[0], self.quality[1] + 1)

        # fg_color, fg_style, bg_color = self._generate_color()

        fg_color = self.color.sample()
        bg_color = (255, 255, 255, 255)
        fg_style = self.style.sample()

        fg_image, label, bboxes = self._generate_text(fg_color, fg_style)

        bg_layer = layers.RectLayer(fg_image.shape[:2][::-1], bg_color)

        self.texture.apply([bg_layer])

        bg_image = bg_layer.output()

        # bg_image = self._generate_background(fg_image.shape[:2][::-1], bg_color)

        image = _blend_images(fg_image, bg_image, self.visibility_check)
        # image = self._postprocess_images(
        #     [image]
        # )[0]

        data = {
            "image": image,
            "label": label,
            "quality": quality,
            "bboxes": bboxes,
            "size": image.shape[:2],
        }

        return data

    def init_save(self, root, mode="w"):
        os.makedirs(root, exist_ok=True)

        gt_path = os.path.join(root, "gt.txt")
        coords_path = os.path.join(root, "coords.txt")

        self.gt_file = open(gt_path, mode, encoding="utf-8")
        if self.coord_output:
            self.coords_file = open(coords_path, mode, encoding="utf-8")

    def save(self, root, data, idx):
        image = data["image"]
        label = data["label"]
        quality = data["quality"]
        bboxes = data["bboxes"]
        size = data["size"]

        image = Image.fromarray(image[..., :3].astype(np.uint8))

        # coords = [[x, y, x + w, y + h] for x, y, w, h in bboxes]
        # coords = "\t".join([",".join(map(str, map(int, coord))) for coord in coords])

        polygons = [bbox_to_polygon(bbox) for bbox in bboxes]

        shard = str(idx // 10000)
        image_key = os.path.join("images", shard, f"{idx}.jpg")
        image_path = os.path.join(root, image_key)

        os.makedirs(os.path.dirname(image_path), exist_ok=True)
        image.save(image_path, quality=quality)

        self.gt_file.write(f"{image_key}\t{label}\n")
        if self.coord_output:
            # self.coords_file.write(f"{image_key}\t{coords}\n")
            self.coords_file.write(f"{image_key}\t({size[1]},{size[0]})\t{polygons}\n")

    def end_save(self, root):
        self.gt_file.close()
        if self.coord_output:
            self.coords_file.close()

    def _generate_color(self):
        fg_style = self.style.sample()

        if fg_style["state"]:
            fg_color, bg_color, style_color = self.colormap3.sample()
            fg_style["meta"]["meta"]["rgb"] = style_color["rgb"]
        else:
            fg_color, bg_color = self.colormap2.sample()

        return fg_color, fg_style, bg_color

    def _generate_text(self, color, style):

        chars = [
            self.corpus.data(self.corpus.sample())
            for _ in range(np.random.randint(self.counts[0], self.counts[1] + 1))
        ]
        # # add random diacritics to the text for augmentation
        # augment_p = 1  # probability of applying augmentation
        # chars = [augment_text(char) if np.random.rand() < augment_p else char for char in chars]
        label = text = " ".join(chars)

        font = self.font.sample({"text": text, "vertical": self.vertical})

        char_layers = [layers.TextLayer(char, **font) for char in chars]

        self.shape.apply(char_layers)

        self.layout.apply(char_layers, {"meta": {"vertical": self.vertical}})

        text_layer = layers.Group(char_layers).merge()

        # transform = self.transform.sample()

        self.color.apply([text_layer], color)

        # self.texture.apply([text_layer])

        self.style.apply([text_layer, *char_layers], style)
        # self.transform.apply(
        #     [text_layer, *char_layers], transform
        # )

        self.fit.apply([text_layer, *char_layers])

        self.pad.apply([text_layer])

        for char_layer in char_layers:
            char_layer.topleft -= text_layer.topleft

        out = text_layer.output()

        bboxes = [char_layer.bbox for char_layer in char_layers]

        return out, label, bboxes

    def _generate_background(self, size, color):
        layer = layers.RectLayer(size)
        self.color.apply([layer], color)
        self.texture.apply([layer])
        out = layer.output()
        return out

    def _erase_image(self, image, mask):
        mask = _create_poly_mask(mask, self.foreground_mask_pad)
        mask_layer = layers.Layer(mask)
        image_layer = layers.Layer(image)
        image_layer.bbox = mask_layer.bbox
        self.midground_offset.apply([image_layer])
        out = image_layer.erase(mask_layer).output(bbox=mask_layer.bbox)
        return out

    def _postprocess_images(self, images):
        image_layers = [layers.Layer(image) for image in images]
        self.postprocess.apply(image_layers)
        outs = [image_layer.output() for image_layer in image_layers]
        return outs


def _blend_images(src, dst, visibility_check=False):
    blend_modes = np.random.permutation(BLEND_MODES)

    for blend_mode in blend_modes:
        out = utils.blend_image(src, dst, mode=blend_mode)

        if not visibility_check or _check_visibility(out, src[..., 3]):

            break
    else:
        raise RuntimeError("Text is not visible")

    return out


def _check_visibility(image, mask):
    #
    gray = utils.to_gray(image[..., :3]).astype(np.uint8)
    mask = mask.astype(np.uint8)
    height, width = mask.shape

    peak = (mask > 127).astype(np.uint8)

    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    bound = (mask > 0).astype(np.uint8)
    bound = cv2.dilate(bound, kernel, iterations=1)

    visit = bound.copy()
    visit ^= 1
    visit = np.pad(visit, 1, constant_values=1)

    border = bound.copy()
    border[mask > 0] = 0

    flag = 4 | cv2.FLOODFILL_FIXED_RANGE | cv2.FLOODFILL_MASK_ONLY

    # Find contours of the peak mask to get one seed point per connected component
    contours, _ = cv2.findContours(peak, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        # Get a starting point inside the contour
        M = cv2.moments(contour)
        if M["m00"] != 0:
            cX = int(M["m10"] / M["m00"])
            cY = int(M["m01"] / M["m00"])
            if peak[cY, cX]:  # Ensure the centroid is exactly on a peak
                cv2.floodFill(gray, visit, (cX, cY), 1, 16, 16, flag)
            else:
                # fallback to the first point of the contour if centroid is outside
                cX, cY = contour[0][0]
                cv2.floodFill(gray, visit, (cX, cY), 1, 16, 16, flag)
        else:
            cX, cY = contour[0][0]
            cv2.floodFill(gray, visit, (cX, cY), 1, 16, 16, flag)

    visit = visit[1:-1, 1:-1]
    count = np.sum(visit & border)
    total = np.sum(border)
    return total > 0 and count <= total * 0.1


def _create_poly_mask(image, pad=0):
    height, width = image.shape[:2]
    alpha = image[..., 3].astype(np.uint8)
    mask = np.zeros((height, width), dtype=np.float32)

    cts, _ = cv2.findContours(alpha, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cts = sorted(cts, key=lambda ct: sum(cv2.boundingRect(ct)[:2]))

    if len(cts) == 1:
        hull = cv2.convexHull(cts[0])
        cv2.fillConvexPoly(mask, hull, 255)

    for idx in range(len(cts) - 1):
        pts = np.concatenate((cts[idx], cts[idx + 1]), axis=0)
        hull = cv2.convexHull(pts)
        cv2.fillConvexPoly(mask, hull, 255)

    mask = utils.dilate_image(mask, pad)
    out = utils.create_image((width, height))
    out[..., 3] = mask
    return out
