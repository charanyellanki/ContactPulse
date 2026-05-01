"""Customer routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.models.customer import Customer
from backend.repositories.customer_repo import (
    CustomerRepository,
    get_customer_repo,
)

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[Customer])
def list_customers(repo: CustomerRepository = Depends(get_customer_repo)) -> list[Customer]:
    return repo.list_customers()


@router.get("/{customer_id}", response_model=Customer)
def get_customer(
    customer_id: str,
    repo: CustomerRepository = Depends(get_customer_repo),
) -> Customer:
    customer = repo.get_customer(customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f"Customer '{customer_id}' not found")
    return customer
