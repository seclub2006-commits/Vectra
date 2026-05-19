# web/routers/market.py
"""
Эндпоинты для получения рыночных данных (свечи, тикер, символы, стакан).
"""

from typing import Dict, Any, List

from fastapi import APIRouter, Depends, Query

from web.dependencies import get_current_user, get_grpc_client
from web.grpc_client import GrpcCoreClient
from web.models import GetCandlesRequest

router = APIRouter(prefix="/api", tags=["market"])


@router.post("/candles")
async def get_candles(
    request: GetCandlesRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить историю свечей OHLCV."""
    candles = await client.get_candles(
        connector=request.connector,
        symbol=request.symbol,
        timeframe=request.timeframe,
        limit=request.limit,
        start_time=request.start_time,
        end_time=request.end_time,
        market_data_source=request.market_data_source,
        market_data_source_config=request.market_data_source_config
    )
    return {"status": "ok", "data": candles}


@router.get("/ticker")
async def get_ticker(
    connector: str = Query(..., description="Имя коннектора"),
    symbol: str = Query(..., description="Торговая пара, например BTCUSDT"),
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить текущий тикер (цена, объём)."""
    ticker = await client.get_ticker(connector, symbol)
    return {"status": "ok", "data": ticker}


@router.get("/symbols")
async def get_symbols(
    connector: str = Query(..., description="Имя коннектора"),
    product_type: str = Query("", description="Тип продукта: SPOT, USDT-FUTURES и т.д."),
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить список доступных торговых пар."""
    symbols = await client.get_symbols(connector, product_type)
    return {"status": "ok", "data": symbols}


@router.get("/orderbook")
async def get_orderbook(
    connector: str = Query(..., description="Имя коннектора"),
    symbol: str = Query(..., description="Торговая пара"),
    depth: int = Query(20, description="Глубина стакана"),
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить стакан ордеров (bids/asks)."""
    ob = await client.get_order_book(connector, symbol, depth)
    return {"status": "ok", "data": ob}