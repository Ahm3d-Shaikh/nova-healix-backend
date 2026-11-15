from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request

from app.container import Container
from app.ridge_container import RidgeContainer


def get_container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


def get_ridge(request: Request) -> RidgeContainer:
    ridge = getattr(request.app.state, "ridge", None)
    if ridge is None:
        raise HTTPException(status_code=503, detail="The RIDGE module is not available")
    return cast(RidgeContainer, ridge)


ContainerDep = Annotated[Container, Depends(get_container)]
RidgeDep = Annotated[RidgeContainer, Depends(get_ridge)]
