"""
@file tax.py
@brief FastAPI routes for ad-hoc tax calculations.

Endpoints:
  POST /api/tax/calculate — calculate net income and all tax deductions
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.engine.tax_engine import TaxResult, calculate_net_income
from backend.models.models import TaxTreatment

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class TaxCalculateRequest(BaseModel):
    """
    @brief Request body for POST /api/tax/calculate.
    @param gross Gross annual income amount.
    @param tax_treatment Tax treatment identifier string.
    @param jurisdiction Tax jurisdiction identifier string.
    @param pension_contributions Pre-tax pension contributions that reduce taxable income.
    @param filing_status US filing status ('single' or 'married').
    """
    model_config = ConfigDict(from_attributes=True)

    gross: float = Field(..., gt=0, description="Gross annual income")
    tax_treatment: str = Field(default="PAYE", description="Tax treatment identifier")
    jurisdiction: str = Field(default="UK", description="Tax jurisdiction")
    pension_contributions: float = Field(default=0.0, ge=0.0)
    filing_status: str = Field(default="single", description="US: 'single' or 'married'")


class TaxCalculateResponse(BaseModel):
    """
    @brief Response for POST /api/tax/calculate.
    @param gross_income Original gross income.
    @param net_income Net take-home income.
    @param income_tax Income tax payable.
    @param ni National Insurance / payroll tax.
    @param effective_rate Combined effective tax rate.
    @param marginal_rate Marginal income tax rate.
    @param breakdown Detailed breakdown dict.
    """
    model_config = ConfigDict(from_attributes=True)

    gross_income: float
    net_income: float
    income_tax: float
    ni: float
    effective_rate: float
    marginal_rate: float
    breakdown: dict = {}


# ── Route handlers ────────────────────────────────────────────────────────────

@router.post("/tax/calculate", response_model=TaxCalculateResponse)
def calculate_tax(body: TaxCalculateRequest, request: Request) -> TaxCalculateResponse:
    """
    @brief Calculate net income and all tax deductions for given parameters.

    Looks up the tax profile matching the jurisdiction from the profiles loaded
    on startup. Returns a full tax breakdown including income tax, NI,
    effective rate, and marginal rate.

    @param body TaxCalculateRequest with gross, tax_treatment, and jurisdiction.
    @param request FastAPI Request (provides access to app.state.tax_profiles).
    @return TaxCalculateResponse with tax breakdown.
    """
    try:
        # Parse tax treatment
        try:
            treatment = TaxTreatment(body.tax_treatment)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid tax_treatment '{body.tax_treatment}'. "
                       f"Valid values: {[t.value for t in TaxTreatment]}",
            )

        # Find matching tax profile
        tax_profiles: dict = request.app.state.tax_profiles
        profile = None

        # Try exact match first, then case-insensitive prefix match on jurisdiction
        jurisdiction_lower = body.jurisdiction.lower()
        for pid, p in tax_profiles.items():
            if p.jurisdiction.value.lower() == jurisdiction_lower:
                profile = p
                break
            # Also try matching by profile id
            if pid.lower().startswith(jurisdiction_lower):
                profile = p

        if profile is None:
            # Last resort: use first available profile and warn
            if tax_profiles:
                profile = next(iter(tax_profiles.values()))
                logger.warning(
                    "calculate_tax: no profile for jurisdiction '%s' — using '%s'",
                    body.jurisdiction, profile.id,
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail="No tax profiles loaded. Check config/tax_profiles.yaml.",
                )

        result: TaxResult = calculate_net_income(
            gross=body.gross,
            tax_treatment=treatment,
            profile=profile,
            pension_contributions=body.pension_contributions,
            filing_status=body.filing_status,
        )

        return TaxCalculateResponse(
            gross_income=result.gross_income,
            net_income=result.net_income,
            income_tax=result.income_tax,
            ni=result.national_insurance,
            effective_rate=result.effective_rate,
            marginal_rate=result.marginal_rate,
            breakdown=result.breakdown,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("calculate_tax: unexpected error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Tax calculation error", "detail": str(exc)},
        )
