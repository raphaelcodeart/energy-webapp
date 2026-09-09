from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user
from app.domains.accounting import service as accounting_service
from app.domains.accounting.schemas import FinancialMovementRead

router = APIRouter(prefix="/accounting", tags=["accounting"])


@router.get("/mine", response_model=list[FinancialMovementRead])
async def get_my_movements(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Any authenticated user reads only their own merged LialCash + real-money
    movements, no permission check beyond authentication -- same pattern as
    GET /wallets/me."""
    return await accounting_service.list_my_movements(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
