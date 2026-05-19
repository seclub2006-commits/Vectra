#!/usr/bin/env python3
"""
Полная проверка всех методов коннекторов Bitget (спот и фьючерсы) в демо-режиме.
Тест не прерывается при ошибках – они логируются, но скрипт продолжает выполнение.
В конце выводится статистика и ожидается нажатие Enter для закрытия.

Для запуска: python test_connectors.py
Переменные окружения (файл .env):
    API_KEY, API_SECRET, API_PASSPHRASE – демо-ключи Bitget
"""

import asyncio
import logging
import os
import sys
from typing import Dict, Any, List, Tuple
from datetime import datetime

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from connectors.bitget.spot import BitgetSpotConnector
from connectors.bitget.futures import BitgetFuturesConnector
from connectors.base.exceptions import APIError, NetworkError

load_dotenv()

DEMO_API_KEY = os.getenv("API_KEY", "")
DEMO_API_SECRET = os.getenv("API_SECRET", "")
DEMO_API_PASSPHRASE = os.getenv("API_PASSPHRASE", "")

SYMBOL_SPOT = "BTCUSDT"
SYMBOL_FUTURES = "BTCUSDT"
TEST_LIMIT_QTY = 0.0001
TEST_MARKET_USDT = 5.0
LIMIT_OFFSET_PERCENT = 5.0

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TEST_RESULTS = {
    "spot": {"pass": 0, "fail": 0, "skip": 0},
    "futures": {"pass": 0, "fail": 0, "skip": 0}
}

def print_section(title: str):
    print("\n" + "="*80)
    print(f" {title}")
    print("="*80)

def safe_call(connector_name: str, method):
    async def wrapper(*args, **kwargs):
        try:
            result = await method(*args, **kwargs)
            if result is not None:
                TEST_RESULTS[connector_name]["pass"] += 1
            else:
                TEST_RESULTS[connector_name]["skip"] += 1
                print(f"   ⏭️ {method.__name__}: вернул None")
            return result
        except (APIError, NetworkError, NotImplementedError) as e:
            if isinstance(e, NotImplementedError):
                TEST_RESULTS[connector_name]["skip"] += 1
                print(f"   ⏭️ {method.__name__}: метод не реализован")
            else:
                skip_codes = ['404', '40307', '43011', '40847', '400172']
                if hasattr(e, 'code') and e.code in skip_codes:
                    TEST_RESULTS[connector_name]["skip"] += 1
                    print(f"   ⏭️ {method.__name__}: {e.code} – {e.message if hasattr(e,'message') else e}")
                else:
                    TEST_RESULTS[connector_name]["fail"] += 1
                    print(f"   ❌ {method.__name__}: {e}")
            return None
        except Exception as e:
            TEST_RESULTS[connector_name]["fail"] += 1
            print(f"   ❌ {method.__name__}: {type(e).__name__} – {e}")
            return None
    return wrapper

async def test_spot_full() -> bool:
    print_section("🔵 ТЕСТ СПОТ КОННЕКТОРА (ДЕМО)")

    config = {
        'api_key': DEMO_API_KEY,
        'api_secret': DEMO_API_SECRET,
        'api_passphrase': DEMO_API_PASSPHRASE,
        'demo': True,
        'product_type': 'SPOT',
    }
    spot = BitgetSpotConnector("demo_spot", config)

    try:
        if not await spot.connect():
            print("❌ Не удалось подключиться")
            TEST_RESULTS["spot"]["fail"] += 1
            return False
        print("✅ Подключение успешно")

        print("\n📊 Рыночные данные:")
        coins = await safe_call("spot", spot.get_coins)()
        if coins:
            print(f"   - get_coins: найдено {len(coins)} монет")
        symbols = await safe_call("spot", spot.get_symbols)()
        if symbols:
            print(f"   - get_symbols: найдено {len(symbols)} пар")
        vip_fee = await safe_call("spot", spot.get_vip_fee_rate)()
        if vip_fee:
            print(f"   - get_vip_fee_rate: получено {len(vip_fee)} уровней")
        ticker = await safe_call("spot", spot.get_ticker)(SYMBOL_SPOT)
        if ticker:
            print(f"   - get_ticker: last={ticker['last']:.2f}")
        tickers = await safe_call("spot", spot.get_tickers)()
        if tickers:
            print(f"   - get_tickers: получено {len(tickers)} тикеров")
        ob = await safe_call("spot", spot.get_order_book)(SYMBOL_SPOT, limit=5)
        if ob:
            print(f"   - get_order_book: bids[0]={ob['bids'][0] if ob['bids'] else 'N/A'}")
        md = await safe_call("spot", spot.get_merge_depth)(SYMBOL_SPOT, precision='scale1', limit=10)
        if md:
            print(f"   - get_merge_depth: scale={md.get('scale')}")
        candles = await safe_call("spot", spot.get_klines)(SYMBOL_SPOT, '1m', limit=3)
        if candles:
            print(f"   - get_klines: получено {len(candles)} свечей")
        if candles:
            end_ts = candles[-1]['timestamp']
            hist = await safe_call("spot", spot.get_history_klines)(SYMBOL_SPOT, '1m', end_ts, limit=50)
            if hist:
                print(f"   - get_history_klines: получено {len(hist)} исторических свечей")
        auction = await safe_call("spot", spot.get_auction)(SYMBOL_SPOT)
        if auction:
            print(f"   - get_auction: stage={auction.get('stage')}")
        trades = await safe_call("spot", spot.get_recent_trades)(SYMBOL_SPOT, limit=5)
        if trades:
            print(f"   - get_recent_trades: получено {len(trades)} сделок")
        if trades:
            last_id = trades[-1]['trade_id']
            hist_trades = await safe_call("spot", spot.get_history_trades)(SYMBOL_SPOT, limit=5, id_less_than=last_id)
            if hist_trades:
                print(f"   - get_history_trades: получено {len(hist_trades)} исторических сделок")

        print("\n💰 Баланс:")
        balances = await safe_call("spot", spot.get_balance)()
        usdt_balance = next((b for b in balances if b['currency'] == 'USDT'), None) if balances else None
        if usdt_balance:
            print(f"   - USDT: available={usdt_balance['available']:.2f}")
        acc_info = await safe_call("spot", spot.get_account_info)()
        if acc_info:
            print(f"   - get_account_info: userId={acc_info.get('userId')}")
        sub_assets = await safe_call("spot", spot.get_subaccount_assets)(limit=5)
        if sub_assets is not None:
            print(f"   - get_subaccount_assets: {len(sub_assets)} субаккаунтов")
        bills = await safe_call("spot", spot.get_account_bills)(limit=5)
        if bills is not None:
            print(f"   - get_account_bills: {len(bills)} записей")
        deduct_info = await safe_call("spot", spot.get_bgb_deduct_info)()
        if deduct_info:
            print(f"   - get_bgb_deduct_info: deduct={deduct_info}")
        await safe_call("spot", spot.switch_bgb_deduct)(True)

        print("\n📝 Торговые ордера:")
        current_price = ticker['last'] if ticker else 50000
        limit_price = round(current_price * (1 - LIMIT_OFFSET_PERCENT / 100), 2)
        order_cost = TEST_LIMIT_QTY * limit_price
        if usdt_balance and usdt_balance['available'] >= order_cost:
            order = await safe_call("spot", spot.create_order)(
                symbol=SYMBOL_SPOT, side='buy', order_type='limit',
                quantity=TEST_LIMIT_QTY, price=limit_price,
                preset_tp=limit_price*1.1, preset_sl=limit_price*0.9
            )
            if order:
                order_id = order['orderId']
                print(f"   - create_order (limit): orderId={order_id}")
                order_info = await safe_call("spot", spot.get_order)(SYMBOL_SPOT, order_id=order_id)
                if order_info:
                    print(f"   - get_order: status={order_info.get('status')}")
                cancel_res = await safe_call("spot", spot.cancel_order)(SYMBOL_SPOT, order_id=order_id)
                if cancel_res:
                    print(f"   - cancel_order: Order cancelled")
        else:
            print(f"   ⚠️ Недостаточно USDT для лимитного ордера (нужно {order_cost:.2f})")

        batch_res = await safe_call("spot", spot.batch_create_orders)(
            order_list=[{'side':'buy','orderType':'limit','price':limit_price,'size':TEST_LIMIT_QTY, 'force':'gtc'}],
            symbol=SYMBOL_SPOT, batch_mode='single'
        )
        if batch_res and batch_res.get('successList'):
            print(f"   - batch_create_orders: успешно {len(batch_res['successList'])} ордеров")
            for ord_info in batch_res['successList']:
                await safe_call("spot", spot.cancel_order)(SYMBOL_SPOT, order_id=ord_info['orderId'])

        await safe_call("spot", spot.cancel_order_by_symbol)(SYMBOL_SPOT)
        print("   - cancel_order_by_symbol: вызван (асинхронно)")

        open_orders = await safe_call("spot", spot.get_open_orders)(SYMBOL_SPOT, limit=10)
        if open_orders is not None:
            print(f"   - get_open_orders: {len(open_orders)} активных ордеров")
        history = await safe_call("spot", spot.get_order_history)(SYMBOL_SPOT, limit=5)
        if history is not None:
            print(f"   - get_order_history: {len(history)} записей")
        fills = await safe_call("spot", spot.get_fills)(SYMBOL_SPOT, limit=5)
        if fills is not None:
            print(f"   - get_fills: {len(fills)} сделок")

        print("\n⏰ Плановые ордера (trigger):")
        trigger_price = round(current_price * 0.95, 2)
        plan_order = await safe_call("spot", spot.place_plan_order)(
            symbol=SYMBOL_SPOT, side='buy', order_type='limit',
            size=TEST_LIMIT_QTY, trigger_price=trigger_price,
            execute_price=trigger_price, client_oid="test_plan_spot"
        )
        if plan_order:
            plan_id = plan_order['orderId']
            print(f"   - place_plan_order: orderId={plan_id}")
            current_plans = await safe_call("spot", spot.get_current_plan_orders)(SYMBOL_SPOT, limit=10)
            if current_plans is not None:
                print(f"   - get_current_plan_orders: {len(current_plans)} активных планов")
            sub_orders = await safe_call("spot", spot.get_plan_sub_order)(plan_id)
            if sub_orders is not None:
                print(f"   - get_plan_sub_order: {len(sub_orders)} под-ордеров")
            cancel_plan = await safe_call("spot", spot.cancel_plan_order)(order_id=plan_id)
            if cancel_plan:
                print(f"   - cancel_plan_order: отменён")
        await safe_call("spot", spot.batch_cancel_plan_orders)(symbol_list=[SYMBOL_SPOT])
        print("   - batch_cancel_plan_orders: вызван")
        history_plans = await safe_call("spot", spot.get_history_plan_orders)(SYMBOL_SPOT, limit=5)
        if history_plans is not None:
            print(f"   - get_history_plan_orders: {len(history_plans)} записей")

        print("\n💸 Переводы и депозиты:")
        await safe_call("spot", spot.get_transferable_coins)('spot', 'usdt_futures')
        print("   - get_transferable_coins: вызван")
        dep_addr = await safe_call("spot", spot.get_deposit_address)('USDT', chain='trc20')
        if dep_addr:
            print(f"   - get_deposit_address: {dep_addr.get('address')[:20] if dep_addr.get('address') else 'N/A'}...")
        dep_records = await safe_call("spot", spot.get_deposit_records)(limit=5)
        if dep_records is not None:
            print(f"   - get_deposit_records: {len(dep_records)} записей")
        wd_records = await safe_call("spot", spot.get_withdrawal_records)(limit=5)
        if wd_records is not None:
            print(f"   - get_withdrawal_records: {len(wd_records)} записей")

        print("\n🔌 WebSocket:")
        try:
            def ws_cb(data):
                pass
            await spot.subscribe_ticker(SYMBOL_SPOT, ws_cb)
            await asyncio.sleep(1)
            await spot.unsubscribe_all(SYMBOL_SPOT)
            print("   - WebSocket подписка/отписка успешна")
            TEST_RESULTS["spot"]["pass"] += 1
        except Exception as e:
            print(f"   ❌ WebSocket: {e}")
            TEST_RESULTS["spot"]["fail"] += 1

        await spot.disconnect()
        print("\n✅ Спот тест завершён")
        return True

    except Exception as e:
        print(f"\n❌ Критическая ошибка спота: {e}")
        import traceback
        traceback.print_exc()
        await spot.disconnect()
        return False

async def test_futures_full() -> bool:
    print_section("🟢 ТЕСТ ФЬЮЧЕРСОВ (USDT-FUTURES, ДЕМО)")

    config = {
        'api_key': DEMO_API_KEY,
        'api_secret': DEMO_API_SECRET,
        'api_passphrase': DEMO_API_PASSPHRASE,
        'demo': True,
        'product_type': 'USDT-FUTURES',
        'margin_coin': 'USDT',
        'margin_mode': 'crossed'
    }
    futures = BitgetFuturesConnector("demo_futures", config)

    try:
        if not await futures.connect():
            print("❌ Не удалось подключиться")
            TEST_RESULTS["futures"]["fail"] += 1
            return False
        print("✅ Подключение успешно")

        try:
            await futures.cleanup_all()
            print("🧹 Очистка выполнена")
        except Exception as e:
            print(f"   Очистка: {e}")

        print("\n💰 Баланс:")
        balances = await safe_call("futures", futures.get_balance)()
        usdt_balance = next((b for b in balances if b['currency'] == 'USDT'), None) if balances else None
        if usdt_balance:
            print(f"   - USDT: available={usdt_balance['available']:.2f}")
        account = await safe_call("futures", futures.get_account)(SYMBOL_FUTURES)
        if account:
            print(f"   - get_account: margin_mode={account.get('margin_mode')}")

        print("\n📊 Рыночные данные:")
        contracts = await safe_call("futures", futures.get_contracts)(symbol=SYMBOL_FUTURES)
        if contracts:
            print(f"   - get_contracts: {len(contracts)} контрактов")
        ticker = await safe_call("futures", futures.get_ticker)(SYMBOL_FUTURES)
        current_price = ticker['last'] if ticker else 50000
        if ticker:
            print(f"   - get_ticker: last={ticker['last']:.2f}")
        tickers = await safe_call("futures", futures.get_tickers)()
        if tickers:
            print(f"   - get_tickers: получено {len(tickers)} тикеров")
        depth = await safe_call("futures", futures.get_merge_depth)(SYMBOL_FUTURES, precision='scale1', limit=5)
        if depth:
            print(f"   - get_merge_depth: bids[0]={depth['bids'][0] if depth['bids'] else 'N/A'}")
        candles = await safe_call("futures", futures.get_klines)(SYMBOL_FUTURES, '1m', limit=3)
        if candles:
            print(f"   - get_klines: получено {len(candles)} свечей")
        if candles:
            end_ts = candles[-1]['timestamp']
            hist = await safe_call("futures", futures.get_historical_klines)(SYMBOL_FUTURES, '1m', end_ts-3600000, end_ts, limit=50)
            if hist:
                print(f"   - get_historical_klines: получено {len(hist)} свечей")
        trades = await safe_call("futures", futures.get_recent_trades)(SYMBOL_FUTURES, limit=5)
        if trades:
            print(f"   - get_recent_trades: {len(trades)} сделок")
        oi = await safe_call("futures", futures.get_open_interest)(SYMBOL_FUTURES)
        if oi:
            print(f"   - get_open_interest: size={oi.get('size', 0):.2f}")
        fr = await safe_call("futures", futures.get_funding_rate)(SYMBOL_FUTURES)
        if fr:
            print(f"   - get_funding_rate: rate={fr.get('funding_rate', 0):.6f}")
        fr_hist = await safe_call("futures", futures.get_funding_history)(SYMBOL_FUTURES, limit=5)
        if fr_hist is not None:
            print(f"   - get_funding_history: {len(fr_hist)} записей")
        ft = await safe_call("futures", futures.get_funding_time)(SYMBOL_FUTURES)
        if ft:
            print(f"   - get_funding_time: next={ft.get('next_funding_time')}")
        mip = await safe_call("futures", futures.get_mark_index_prices)(SYMBOL_FUTURES)
        if mip:
            print(f"   - get_mark_index_prices: mark={mip.get('mark_price', 0):.2f}")
        oi_limit = await safe_call("futures", futures.get_oi_limit)(SYMBOL_FUTURES)
        if oi_limit is not None:
            print(f"   - get_oi_limit: {len(oi_limit)} записей")
        pos_tier = await safe_call("futures", futures.get_position_tier)(SYMBOL_FUTURES)
        if pos_tier is not None:
            print(f"   - get_position_tier: {len(pos_tier)} уровней")

        print("\n⚙️ Управление плечом и режимами:")
        lev_res = await safe_call("futures", futures.set_leverage)(SYMBOL_FUTURES, 10, margin_mode='crossed')
        if lev_res:
            print(f"   - set_leverage: cross_leverage={lev_res.get('cross_leverage')}")
        pos_mode_res = await safe_call("futures", futures.set_position_mode)('one_way_mode')
        if pos_mode_res:
            print(f"   - set_position_mode: {pos_mode_res.get('pos_mode')}")
        max_open = await safe_call("futures", futures.get_max_openable)(SYMBOL_FUTURES, 'long', 'market')
        if max_open:
            print(f"   - get_max_openable: {max_open.get('max_open', 0):.6f}")
        liq = await safe_call("futures", futures.get_liquidation_price)(SYMBOL_FUTURES, 'long', 'market', open_amount=10)
        if liq:
            print(f"   - get_liquidation_price: {liq.get('liquidation_price', 0):.2f}")
        est = await safe_call("futures", futures.get_estimated_open_count)(SYMBOL_FUTURES, open_amount=10, open_price=current_price, leverage=10)
        if est:
            print(f"   - get_estimated_open_count: size={est.get('size', 0):.6f}")

        print("\n📌 Позиции (до открытия):")
        positions = await safe_call("futures", futures.get_positions)()
        if positions is not None:
            print(f"   - get_positions: {len(positions)} открытых позиций")
        adl = await safe_call("futures", futures.get_position_adl_rank)()
        if adl is not None:
            print(f"   - get_position_adl_rank: {len(adl)} записей")

        print("\n🚀 Открытие позиции:")
        if usdt_balance and usdt_balance['available'] >= TEST_MARKET_USDT:
            size_to_open = (TEST_MARKET_USDT * 10) / current_price
            order = await safe_call("futures", futures.create_order)(
                symbol=SYMBOL_FUTURES, side='buy', order_type='market', quantity=size_to_open
            )
            if order:
                print(f"   - create_order: orderId={order['orderId']}")
                await asyncio.sleep(3)
                pos_after = await safe_call("futures", futures.get_single_position)(SYMBOL_FUTURES)
                if pos_after:
                    print(f"   - get_single_position: side={pos_after.get('side')}, size={pos_after.get('size', 0):.6f}")
                    entry = pos_after['entry_price']
                    size = pos_after['size']

                    print("\n🎯 Установка TP/SL:")
                    tp_price = round(entry * 1.02, 1)
                    sl_price = round(entry * 0.98, 1)
                    tp_res = await safe_call("futures", futures.set_tpsl)(SYMBOL_FUTURES, 'long', tp_price, 0, 'profit_plan', size)
                    if tp_res:
                        print(f"   - set_tpsl (TP): orderId={tp_res.get('orderId')}")
                    sl_res = await safe_call("futures", futures.set_tpsl)(SYMBOL_FUTURES, 'long', sl_price, 0, 'loss_plan', size)
                    if sl_res:
                        print(f"   - set_tpsl (SL): orderId={sl_res.get('orderId')}")

                    print("\n📌 Плановые ордера:")
                    trigger_order = await safe_call("futures", futures.place_trigger_order)(
                        symbol=SYMBOL_FUTURES, side='sell', trade_side='close',
                        order_type='market', size=size/2, trigger_price=round(entry*0.99,1),
                        reduce_only=True
                    )
                    if trigger_order:
                        print(f"   - place_trigger_order: orderId={trigger_order.get('orderId')}")
                        await asyncio.sleep(0.5)
                        await safe_call("futures", futures.cancel_trigger_order)(SYMBOL_FUTURES, order_id=trigger_order['orderId'])
                        print("   - cancel_trigger_order: отменён")
                    trail = await safe_call("futures", futures.place_trailing_stop)(
                        symbol=SYMBOL_FUTURES, side='sell', trade_side='close',
                        callback_rate=0.5, trigger_price=entry, size=size/2
                    )
                    if trail:
                        print(f"   - place_trailing_stop: orderId={trail.get('orderId')}")
                        await safe_call("futures", futures.cancel_trigger_order)(SYMBOL_FUTURES, order_id=trail['orderId'])

                    trigger_list = await safe_call("futures", futures.get_trigger_orders)(SYMBOL_FUTURES, plan_type='normal_plan')
                    if trigger_list is not None:
                        print(f"   - get_trigger_orders: {len(trigger_list)} активных планов")
                    hist_trigger = await safe_call("futures", futures.get_history_trigger_orders)(SYMBOL_FUTURES, limit=5)
                    if hist_trigger is not None:
                        print(f"   - get_history_trigger_orders: {len(hist_trigger)} записей")

                    print("\n🔒 Закрытие позиции:")
                    close_res = await safe_call("futures", futures.close_position)(SYMBOL_FUTURES, 'long')
                    if close_res:
                        print(f"   - close_position: выполнено")
                        await asyncio.sleep(1)
                else:
                    print("   ⚠️ Позиция не открылась")
            else:
                print("   ⚠️ Не удалось открыть позицию")
        else:
            print(f"   ⚠️ Недостаточно USDT для открытия позиции (нужно {TEST_MARKET_USDT})")

        print("\n📜 История:")
        order_hist = await safe_call("futures", futures.get_order_history)(SYMBOL_FUTURES, limit=5)
        if order_hist is not None:
            print(f"   - get_order_history: {len(order_hist)} записей")
        fills = await safe_call("futures", futures.get_fills)(SYMBOL_FUTURES, limit=5)
        if fills is not None:
            print(f"   - get_fills: {len(fills)} сделок")
        hist_positions = await safe_call("futures", futures.get_historical_positions)(SYMBOL_FUTURES, limit=5)
        if hist_positions is not None:
            print(f"   - get_historical_positions: {len(hist_positions)} записей")

        print("\n📁 Дополнительно:")
        isolated = await safe_call("futures", futures.get_isolated_symbols)()
        if isolated is not None:
            print(f"   - get_isolated_symbols: {len(isolated)} символов")
        bills = await safe_call("futures", futures.get_account_bills)(limit=5)
        if bills is not None:
            print(f"   - get_account_bills: {len(bills)} записей")
        interest_hist = await safe_call("futures", futures.get_interest_history)(coin='USDT', limit=5)
        if interest_hist is not None:
            print(f"   - get_interest_history: {len(interest_hist.get('interestList', []))} записей")
        union_cfg = await safe_call("futures", futures.get_union_config)()
        if union_cfg:
            print(f"   - get_union_config: imr={union_cfg.get('imr')}")
        switch_usdt = await safe_call("futures", futures.get_switch_union_usdt)()
        if switch_usdt:
            print(f"   - get_switch_union_usdt: usdtAmount={switch_usdt.get('usdtAmount')}")

        print("\n🔌 WebSocket:")
        try:
            def ws_cb(data):
                pass
            await futures.subscribe_ticker(SYMBOL_FUTURES, ws_cb)
            await asyncio.sleep(1)
            await futures.unsubscribe_all(SYMBOL_FUTURES)
            print("   - WebSocket подписка/отписка успешна")
            TEST_RESULTS["futures"]["pass"] += 1
        except Exception as e:
            print(f"   ❌ WebSocket: {e}")
            TEST_RESULTS["futures"]["fail"] += 1

        await futures.disconnect()
        print("\n✅ Фьючерсный тест завершён")
        return True

    except Exception as e:
        print(f"\n❌ Критическая ошибка фьючерсов: {e}")
        import traceback
        traceback.print_exc()
        await futures.disconnect()
        return False

async def main():
    print("🚀 ПОЛНАЯ ПРОВЕРКА КОННЕКТОРОВ BITGET V2 API (ДЕМО-РЕЖИМ)")
    print("⚠️  Убедитесь, что в .env указаны ДЕМО-ключи и демо-счёт пополнен.\n")

    await test_spot_full()
    await test_futures_full()

    print("\n" + "="*80)
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print("="*80)
    for product, stats in TEST_RESULTS.items():
        total = stats['pass'] + stats['fail'] + stats['skip']
        print(f"{product.upper()}: ✅ {stats['pass']} | ❌ {stats['fail']} | ⏭️ {stats['skip']} (всего {total})")
    print("\nПримечание: Пропущенные методы могут означать, что они не реализованы в коннекторе или требуют особых условий.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Тест прерван пользователем.")
    finally:
        # Ожидание нажатия Enter перед закрытием
        input("\nНажмите Enter для выхода...")