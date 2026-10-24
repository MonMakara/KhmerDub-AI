import logging
from fastapi import APIRouter, HTTPException

from app.core.credentials import (
    save_api_key,
    remove_api_key,
    get_masked_api_key,
    is_api_key_configured,
)
from app.schemas.project import (
    TranslationProviderListResponse,
    TranslationProviderResponse,
    TranslationStyleOption,
    TestConnectionRequest,
    TestConnectionResponse,
    SaveCredentialsRequest,
)
from app.services.translation.registry import (
    list_translation_providers,
    test_provider_connection,
    DEFAULT_TRANSLATION_PROVIDER,
    DEFAULT_TRANSLATION_STYLE,
    validate_translation_provider,
)
from app.services.translation.prompts import TRANSLATION_STYLES

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/providers", response_model=TranslationProviderListResponse)
def get_translation_providers() -> TranslationProviderListResponse:
    """Retrieve all available translation providers with configuration status."""
    raw_providers = list_translation_providers()
    providers = [TranslationProviderResponse(**p) for p in raw_providers]

    styles = [
        TranslationStyleOption(id=k, label=v["label"], description=v["description"])
        for k, v in TRANSLATION_STYLES.items()
    ]

    return TranslationProviderListResponse(
        providers=providers,
        default_provider=DEFAULT_TRANSLATION_PROVIDER,
        default_style=DEFAULT_TRANSLATION_STYLE,
        styles=styles,
    )


@router.post("/test-connection", response_model=TestConnectionResponse)
def test_connection(payload: TestConnectionRequest) -> TestConnectionResponse:
    """Test connection and authentication for a specific AI translation provider."""
    provider = payload.provider.strip().lower()
    if not validate_translation_provider(provider):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported translation provider '{provider}'",
        )

    success, message = test_provider_connection(
        provider_name=provider,
        api_key=payload.api_key,
        model=payload.model,
        base_url=payload.base_url,
    )

    return TestConnectionResponse(
        success=success,
        message=message,
        provider=provider,
    )


@router.post("/credentials")
def set_credentials(payload: SaveCredentialsRequest):
    """Securely save and encrypt an API key for a translation provider."""
    provider = payload.provider.strip().lower()
    if not validate_translation_provider(provider):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported translation provider '{provider}'",
        )

    save_api_key(
        provider,
        payload.api_key,
        base_url=payload.base_url,
        model=payload.model,
    )
    return {
        "success": True,
        "provider": provider,
        "is_configured": is_api_key_configured(provider),
        "masked_key": get_masked_api_key(provider),
        "base_url": payload.base_url,
        "configured_model": payload.model,
    }


@router.delete("/credentials/{provider}")
def delete_credentials(provider: str):
    """Remove stored API key for a translation provider."""
    p_norm = provider.strip().lower()
    if not validate_translation_provider(p_norm):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported translation provider '{p_norm}'",
        )

    remove_api_key(p_norm)
    return {
        "success": True,
        "provider": p_norm,
        "is_configured": is_api_key_configured(p_norm),
    }
