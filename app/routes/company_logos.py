from fastapi import APIRouter, Response

from app.services.logo_storage import read_logo

router = APIRouter()


@router.get("/uploads/company-logos/{filename}", include_in_schema=False)
def company_logo(filename: str):
    contents = read_logo(filename)
    content_type = {
        "png": "image/png", "jpg": "image/jpeg", "webp": "image/webp",
    }[filename.rsplit(".", 1)[1]]
    return Response(contents, media_type=content_type, headers={
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
    })
