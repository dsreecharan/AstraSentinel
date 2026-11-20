from datetime import datetime, timedelta
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def require_utc(value: object) -> object:
    if isinstance(value, str) and "T" in value and value.endswith("Z"):
        return value
    if isinstance(value, datetime) and value.utcoffset() == timedelta(0):
        return value
    raise ValueError("timestamps must be ISO 8601 UTC with a Z suffix")


NonemptyString = Annotated[str, Field(strict=True, min_length=1)]
Sha256 = Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{64}$")]
NonnegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonnegativeFloat = Annotated[float, Field(strict=True, ge=0)]
Confidence = Annotated[float, Field(strict=True, ge=0, le=1)]
UtcTimestamp = Annotated[AwareDatetime, BeforeValidator(require_utc)]
