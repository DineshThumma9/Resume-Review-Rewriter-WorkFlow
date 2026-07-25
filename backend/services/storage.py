import asyncio
import logging

import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url

from core.config import settings

logger = logging.getLogger(__name__)

cloudinary.config()._load_from_url(settings.cloudinary_url)
cloudinary.config(secure=True)


async def upload_pdf_to_cloudinary(pdf_bytes: bytes, filename: str) -> dict:
    try:
        response = await asyncio.to_thread(
            cloudinary.uploader.upload,
            pdf_bytes,
            resource_type="image",
            public_id=filename.replace(".pdf", ""),
            format="pdf",
        )

        pdf_url = response.get("secure_url")
        public_id = response.get("public_id")

        image_url, _options = cloudinary_url(
            f"{public_id}.jpg",
            width=800,
            crop="scale",
            quality="auto",
            fetch_format="jpg",
        )

        return {"pdf_url": pdf_url, "preview_image_url": image_url}
    except Exception as e:
        logger.error(f"Cloudinary Upload Error: {e}")
        return {"pdf_url": None, "preview_image_url": None}
