"""RE-DACT model downloader script (AGENTS.md sections 3 & 8).

Pre-downloads GLiNER and PaddleOCR models into local cache so the pipeline
can run 100% offline without any network access at runtime.
"""

from __future__ import annotations

import os
import numpy as np

# Disable PaddleX network checks during download
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"


def download():
    print("[RE-DACT Setup] 1/2 Downloading GLiNER model: urchade/gliner_multi_pii-v1...")
    from gliner import GLiNER
    GLiNER.from_pretrained("urchade/gliner_multi_pii-v1")
    print("[RE-DACT Setup] GLiNER model cached successfully.")

    print("[RE-DACT Setup] 2/2 Downloading PaddleOCR PP-OCRv6 models...")
    from paddleocr import PaddleOCR
    engine = PaddleOCR(
        lang="en",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    # Warm up with a blank array to ensure weights are extracted and ready
    dummy = np.ones((60, 200, 3), dtype=np.uint8) * 255
    engine.predict(dummy)
    print("[RE-DACT Setup] PaddleOCR models cached successfully.")

    print("\n[RE-DACT Setup] All models are pre-cached. System is ready for 100% offline execution.")


if __name__ == "__main__":
    download()
