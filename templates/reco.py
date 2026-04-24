"""
SynthTIGER
Copyright (c) 2021-present NAVER Corp.
MIT license
"""

import os

import numpy as np
from PIL import Image

from synthtiger import components, layers, templates

class Reco(templates.Template):
    def __init__(self, config=None):
        if config is None:
            config = {}

        self.count = config.get("count", 100)
        self.corpus = components.SecondBaseCorpus(**config.get("corpus", {}))
        self.font = components.BaseFont(**config.get("font", {}))
        self.color = components.RGB(**config.get("color", {}))
        self.layout = components.FlowLayout(**config.get("layout", {}))
        self.fit = components.Fit()

    def generate(self, key=None):
        label = self.corpus.data(self.corpus.sample(key=key))
        # label = self.corpus.data(self.corpus.sample())
        # Provide the full text directly without character splitting
        text = label
        color = self.color.data(self.color.sample())
        font = self.font.sample({"text": text})
        
        text_layer = layers.TextLayer(text, **font, color=color)
        self.layout.apply([text_layer], {"meta": {"vertical": False}})
        
        # self.fit.apply([text_layer])

        bg_layer = layers.RectLayer(text_layer.size, (255, 255, 255, 255))
        bg_layer.topleft = text_layer.topleft

        image = (text_layer + bg_layer).output()

        data = {
            "image": image,
            "label": label,
        }

        return data

    def init_save(self, root, mode="w"):
        os.makedirs(root, exist_ok=True)
        gt_path = os.path.join(root, "gt.txt")
        
        self.gt_file = open(gt_path, mode, encoding="utf-8")

    def save(self, root, data, idx):
        image = data["image"]
        label = data["label"]

        shard = str(idx // 10000)
        image_key = os.path.join("images", shard, f"{idx}.jpg")
        image_path = os.path.join(root, image_key)

        os.makedirs(os.path.dirname(image_path), exist_ok=True)
        image = Image.fromarray(image[..., :3].astype(np.uint8))
        image.save(image_path, quality=95)

        self.gt_file.write(f"{image_key}\t{label}\n")

    def end_save(self, root):
        self.gt_file.close()

