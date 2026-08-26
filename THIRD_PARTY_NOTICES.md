# Third-party notices

`payable-receipt-ocr` calls or depends on the following open-source projects. They are not
relicensed by this repository.

| Project | Role | License |
| --- | --- | --- |
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) | Local OCR executable | Apache-2.0 |
| [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) | Required `eng` and `Devanagari` script models (downloaded by `scripts/setup-models.sh`; not bundled) | Apache-2.0 |
| [OpenCV](https://github.com/opencv/opencv) | Image preprocessing | Apache-2.0 |
| [NumPy](https://github.com/numpy/numpy) | Pixel arrays and numeric operations | BSD-3-Clause |
| [Pillow](https://github.com/python-pillow/Pillow) | Image loading and orientation | HPND |

The trained model files (`eng.traineddata` and `Devanagari.traineddata`) are not distributed with
this package. They are downloaded separately by `scripts/setup-models.sh` from the
[`tessdata_fast`](https://github.com/tesseract-ocr/tessdata_fast) repository at a pinned commit
and verified by SHA-256 checksum.

Consult each dependency's distributed license and notice files when redistributing binaries,
containers, or trained-data files.
