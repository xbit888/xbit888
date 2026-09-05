#!/usr/bin/env python3
"""
CA Watcher — live-трекер покупок/продаж токена по CA.
Тёмный интерфейс в стиле трейдинг-терминалов, с переключением языка (RU/EN/中文).

Двойной клик по файлу (если .pyw ассоциирован с pythonw.exe) открывает окно
без консоли. Если не открывается двойным кликом, запустите из терминала:
    python ca_watcher_gui.pyw

Источники данных — публичные и бесплатные, без ключей и кошельков:
  - frontend-api-v3.pump.fun — статус bonding curve
  - публичный RPC сети (Solana / Ethereum / BSC / Base / Arbitrum / Robinhood / ...)
  - api.dexscreener.com — метаданные токена/пары после миграции на DEX
"""

import json
import queue
import re
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import ttk, font as tkfont
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Локализация
# ---------------------------------------------------------------------------

LANGS = ["ru", "en", "zh"]
LANG_NAMES = {"ru": "RU", "en": "EN", "zh": "中文"}

TR = {
    "app_title": {"ru": "XBIT888", "en": "XBIT888", "zh": "XBIT888"},
    "app_subtitle": {"ru": "live-трекер сделок по адресу токена", "en": "live token-trade watcher", "zh": "代币实时交易监控"},
    "ca_label": {"ru": "Адрес токена (CA)", "en": "Token address (CA)", "zh": "代币地址 (CA)"},
    "ca_placeholder": {"ru": "Вставьте CA и нажмите Пуск", "en": "Paste CA and press Start", "zh": "粘贴代币地址并点击开始"},
    "interval_label": {"ru": "Интервал, с", "en": "Interval, s", "zh": "刷新间隔(秒)"},
    "start": {"ru": "▶ ПУСК", "en": "▶ START", "zh": "▶ 开始"},
    "stop": {"ru": "■ СТОП", "en": "■ STOP", "zh": "■ 停止"},
    "clear": {"ru": "Очистить", "en": "Clear", "zh": "清除"},
    "lang_label": {"ru": "Язык", "en": "Language", "zh": "语言"},

    "status_ready": {"ru": "Готов", "en": "Ready", "zh": "就绪"},
    "status_running": {"ru": "Работает", "en": "Running", "zh": "运行中"},
    "status_stopped": {"ru": "Остановлено", "en": "Stopped", "zh": "已停止"},
    "status_enter_ca": {"ru": "Введите CA токена", "en": "Enter a token CA", "zh": "请输入代币地址"},

    "col_time": {"ru": "Время", "en": "Time", "zh": "时间"},
    "col_type": {"ru": "Тип", "en": "Type", "zh": "类型"},
    "col_wallet": {"ru": "Кошелёк", "en": "Wallet", "zh": "钱包"},
    "col_amount": {"ru": "Токены", "en": "Tokens", "zh": "代币数量"},
    "col_value": {"ru": "Сумма", "en": "Value", "zh": "价值"},
    "col_tx": {"ru": "Транзакция", "en": "Tx", "zh": "交易"},
    "hint_click": {"ru": "Двойной клик: кошелёк — скопировать, транзакция — открыть в браузере",
                   "en": "Double-click: wallet — copy, tx — open in browser",
                   "zh": "双击：钱包—复制地址，交易—在浏览器中打开"},
    "copied": {"ru": "Скопировано: {value}", "en": "Copied: {value}", "zh": "已复制：{value}"},

    "trade_buy": {"ru": "ПОКУПКА", "en": "BUY", "zh": "买入"},
    "trade_sell": {"ru": "ПРОДАЖА", "en": "SELL", "zh": "卖出"},

    "meta_name": {"ru": "Токен", "en": "Token", "zh": "代币"},
    "meta_network": {"ru": "Сеть", "en": "Network", "zh": "网络"},
    "meta_dex": {"ru": "DEX", "en": "DEX", "zh": "交易所"},
    "meta_price": {"ru": "Цена", "en": "Price", "zh": "价格"},
    "meta_liquidity": {"ru": "Ликвидность", "en": "Liquidity", "zh": "流动性"},
    "meta_source_pumpfun": {"ru": "pump.fun (bonding curve)", "en": "pump.fun (bonding curve)", "zh": "pump.fun（联合曲线）"},
    "meta_placeholder": {"ru": "—", "en": "—", "zh": "—"},

    "log_invalid_ca": {"ru": "Не похоже на адрес токена (Solana mint или EVM 0x...).",
                        "en": "Doesn't look like a token address (Solana mint or EVM 0x...).",
                        "zh": "地址格式不正确（应为 Solana mint 或 EVM 0x... 地址）。"},
    "log_checking_pumpfun": {"ru": "Проверяю pump.fun для {ca}...",
                              "en": "Checking pump.fun for {ca}...",
                              "zh": "正在通过 pump.fun 查询 {ca} ..."},
    "log_checking_dexscreener": {"ru": "Ищу информацию о токене через Dexscreener...",
                                  "en": "Looking up the token on Dexscreener...",
                                  "zh": "正在通过 Dexscreener 查询代币信息..."},
    "log_dexscreener_error": {"ru": "Не удалось обратиться к Dexscreener: {e}",
                               "en": "Could not reach Dexscreener: {e}",
                               "zh": "无法连接 Dexscreener: {e}"},
    "log_no_pair": {"ru": "Нет торговой пары для этого адреса (токен новый / нет ликвидности).",
                     "en": "No trading pair found for this address (new token / no liquidity).",
                     "zh": "未找到该地址的交易对（代币过新或无流动性）。"},
    "log_v4_detected": {"ru": "Обнаружен Uniswap V4 (сеть: {chain}). Ищу PoolManager...",
                         "en": "Uniswap V4 detected (network: {chain}). Locating PoolManager...",
                         "zh": "检测到 Uniswap V4（网络：{chain}）。正在查找 PoolManager..."},
    "log_v4_poolmanager_not_found": {"ru": "Не удалось найти PoolManager (возможно, у токена ещё не было сделок).",
                                      "en": "Could not locate PoolManager (the token may not have traded yet).",
                                      "zh": "未能找到 PoolManager（该代币可能尚无交易）。"},
    "log_unknown_chain": {"ru": "Неизвестная сеть '{chain}'.",
                           "en": "Unknown network '{chain}'.",
                           "zh": "未知网络 '{chain}'。"},
    "log_watching_pumpfun": {"ru": "Слежу за bonding curve: {addr}",
                              "en": "Watching bonding curve: {addr}",
                              "zh": "正在监控联合曲线：{addr}"},
    "log_watching_solana": {"ru": "Слежу за пулом (Solana): {addr}",
                             "en": "Watching pool (Solana): {addr}",
                             "zh": "正在监控资金池（Solana）：{addr}"},
    "log_watching_evm": {"ru": "Слежу за парой (EVM): {addr}",
                          "en": "Watching pair (EVM): {addr}",
                          "zh": "正在监控交易对（EVM）：{addr}"},
    "log_watching_v4": {"ru": "Слежу за пулом Uniswap V4: {addr}",
                         "en": "Watching Uniswap V4 pool: {addr}",
                         "zh": "正在监控 Uniswap V4 资金池：{addr}"},
    "log_poolmanager_label": {"ru": "PoolManager: {addr}", "en": "PoolManager: {addr}", "zh": "PoolManager: {addr}"},
    "log_rpc_error": {"ru": "Ошибка RPC ({e}), повтор через {interval}с",
                       "en": "RPC error ({e}), retrying in {interval}s",
                       "zh": "RPC 错误（{e}），{interval} 秒后重试"},
    "log_block_number_error": {"ru": "Не удалось получить номер блока: {e}",
                                "en": "Could not fetch block number: {e}",
                                "zh": "无法获取区块高度：{e}"},
    "log_eth_getlogs_error": {"ru": "Ошибка eth_getLogs ({e}), повтор через {interval}с",
                               "en": "eth_getLogs error ({e}), retrying in {interval}s",
                               "zh": "eth_getLogs 错误（{e}），{interval} 秒后重试"},
    "log_pumpfun_migrated": {"ru": "Токен мигрировал на DEX — нажмите Стоп и Пуск заново.",
                              "en": "Token migrated to a DEX — press Stop then Start again.",
                              "zh": "代币已迁移到 DEX——请点击停止后重新开始。"},
    "log_unexpected_error": {"ru": "Неожиданная ошибка: {e}", "en": "Unexpected error: {e}", "zh": "发生意外错误：{e}"},

    "live": {"ru": "LIVE", "en": "LIVE", "zh": "LIVE"},
    "offline": {"ru": "ОСТАНОВЛЕНО", "en": "OFFLINE", "zh": "已停止"},
    "waiting": {"ru": "ожидание токена...", "en": "waiting for a token...", "zh": "等待代币..."},
    "header_stat_buys": {"ru": "ПОКУПКИ", "en": "BUYS", "zh": "买入"},
    "header_stat_sells": {"ru": "ПРОДАЖИ", "en": "SELLS", "zh": "卖出"},
    "header_stat_clock": {"ru": "ВРЕМЯ", "en": "CLOCK", "zh": "时间"},

    "card_token_info": {"ru": "ТОКЕН", "en": "TOKEN INFO", "zh": "代币信息"},
    "card_live_feed": {"ru": "ЛЕНТА СДЕЛОК", "en": "LIVE FEED", "zh": "实时交易"},
    "card_live_stats": {"ru": "СТАТИСТИКА", "en": "LIVE STATS", "zh": "实时统计"},

    "row_network": {"ru": "СЕТЬ", "en": "NETWORK", "zh": "网络"},
    "row_dex": {"ru": "DEX", "en": "DEX", "zh": "交易所"},
    "row_price": {"ru": "ЦЕНА", "en": "PRICE", "zh": "价格"},
    "row_liquidity": {"ru": "ЛИКВИДНОСТЬ", "en": "LIQUIDITY", "zh": "流动性"},

    "last_price_label": {"ru": "MCAP", "en": "MCAP", "zh": "MCAP"},
    "no_chart_data": {"ru": "нет данных для графика", "en": "no chart data yet", "zh": "暂无图表数据"},

    "stat_buy_volume": {"ru": "Объём покупок", "en": "Buy volume", "zh": "买入量"},
    "stat_sell_volume": {"ru": "Объём продаж", "en": "Sell volume", "zh": "卖出量"},
    "stat_net_flow": {"ru": "ЧИСТЫЙ ПОТОК", "en": "NET FLOW", "zh": "净流入"},
}


class Translator:
    def __init__(self, lang="ru"):
        self.lang = lang

    def t(self, key, **kwargs):
        table = TR.get(key, {})
        template = table.get(self.lang) or table.get("en") or key
        try:
            return template.format(**kwargs)
        except Exception:
            return template


# ---------------------------------------------------------------------------
# Константы / общие HTTP-хелперы
# ---------------------------------------------------------------------------

DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/{}"

DEFAULT_EVM_RPCS = {
    "ethereum": "https://eth.llamarpc.com",
    "bsc": "https://bsc-dataseed.binance.org",
    "base": "https://mainnet.base.org",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "polygon": "https://polygon-rpc.com",
    "avalanche": "https://api.avax.network/ext/bc/C/rpc",
    "optimism": "https://mainnet.optimism.io",
    "robinhood": "https://rpc.mainnet.chain.robinhood.com",
}

DEFAULT_SOLANA_RPC = "https://api.mainnet-beta.solana.com"
PUMPFUN_COIN_URL = "https://frontend-api-v3.pump.fun/coins/{}"
PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

EXPLORER_TX = {
    "solana": "https://solscan.io/tx/{}",
    "ethereum": "https://etherscan.io/tx/{}",
    "bsc": "https://bscscan.com/tx/{}",
    "base": "https://basescan.org/tx/{}",
    "arbitrum": "https://arbiscan.io/tx/{}",
    "polygon": "https://polygonscan.com/tx/{}",
    "avalanche": "https://snowtrace.io/tx/{}",
    "optimism": "https://optimistic.etherscan.io/tx/{}",
    "robinhood": "https://robinhoodchain.blockscout.com/tx/{}",
}
EXPLORER_ADDRESS = {
    "solana": "https://solscan.io/account/{}",
    "ethereum": "https://etherscan.io/address/{}",
    "bsc": "https://bscscan.com/address/{}",
    "base": "https://basescan.org/address/{}",
    "arbitrum": "https://arbiscan.io/address/{}",
    "polygon": "https://polygonscan.com/address/{}",
    "avalanche": "https://snowtrace.io/address/{}",
    "optimism": "https://optimistic.etherscan.io/address/{}",
    "robinhood": "https://robinhoodchain.blockscout.com/address/{}",
}


def explorer_tx_url(chain_id, tx_hash):
    template = EXPLORER_TX.get(chain_id)
    return template.format(tx_hash) if template else tx_hash


def explorer_address_url(chain_id, address):
    template = EXPLORER_ADDRESS.get(chain_id)
    return template.format(address) if template else address

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
UNISWAP_V4_SWAP_TOPIC = "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f"

EVM_CA_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
SOLANA_CA_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def http_get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "ca-watcher/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post_json(url, payload, timeout=15):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", "User-Agent": "ca-watcher/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def detect_chain_by_format(ca):
    if EVM_CA_RE.match(ca):
        return "evm"
    if SOLANA_CA_RE.match(ca):
        return "solana"
    return None


def fetch_dexscreener_info(ca):
    data = http_get_json(DEXSCREENER_TOKEN_URL.format(ca))
    pairs = data.get("pairs") or []
    if not pairs:
        return None
    pairs.sort(key=lambda p: (p.get("liquidity") or {}).get("usd", 0) or 0, reverse=True)
    best = pairs[0]
    return {
        "chainId": best.get("chainId"),
        "dexId": best.get("dexId"),
        "pairAddress": best.get("pairAddress"),
        "baseToken": best.get("baseToken", {}),
        "quoteToken": best.get("quoteToken", {}),
        "priceUsd": best.get("priceUsd"),
        "priceNative": best.get("priceNative"),
        "liquidityUsd": (best.get("liquidity") or {}).get("usd"),
        "marketCapUsd": best.get("marketCap") or best.get("fdv"),
        "url": best.get("url"),
    }


# ---------------------------------------------------------------------------
# pump.fun bonding curve
# ---------------------------------------------------------------------------

def fetch_pumpfun_info(mint):
    try:
        return http_get_json(PUMPFUN_COIN_URL.format(mint), timeout=10)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def verify_pumpfun_curve(rpc_url, bonding_curve):
    try:
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
            "params": [bonding_curve, {"encoding": "base64"}],
        }
        resp = http_post_json(rpc_url, payload, timeout=10)
        value = (resp.get("result") or {}).get("value")
        return bool(value) and value.get("owner") == PUMP_PROGRAM_ID
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return False


def pumpfun_extract_trade(tx, curve_pda, assoc_curve, decimals=6):
    if not tx or not tx.get("meta") or tx["meta"].get("err"):
        return None
    msg = tx["transaction"]["message"]
    program_ids = [ix.get("programId") for ix in msg.get("instructions", [])]
    if PUMP_PROGRAM_ID not in program_ids:
        return None
    outer_idx = program_ids.index(PUMP_PROGRAM_ID)

    inner_ixs = []
    for grp in tx["meta"].get("innerInstructions") or []:
        if grp.get("index") == outer_idx:
            inner_ixs = grp.get("instructions") or []
            break
    if not inner_ixs:
        return None

    is_buy = None
    token_amount_raw = None
    for ix in inner_ixs:
        if ix.get("program") != "spl-token":
            continue
        parsed = ix.get("parsed") or {}
        if parsed.get("type") not in ("transfer", "transferChecked"):
            continue
        info = parsed.get("info", {})
        amount = info.get("amount")
        if amount is None and "tokenAmount" in info:
            amount = info["tokenAmount"].get("amount")
        if info.get("source") == assoc_curve:
            is_buy, token_amount_raw = True, amount
        elif info.get("destination") == assoc_curve:
            is_buy, token_amount_raw = False, amount

    if is_buy is None:
        return None

    sol_candidates = []
    for ix in inner_ixs:
        if ix.get("program") != "system":
            continue
        parsed = ix.get("parsed") or {}
        if parsed.get("type") != "transfer":
            continue
        info = parsed.get("info", {})
        if is_buy and info.get("destination") == curve_pda:
            sol_candidates.append(info)
        elif not is_buy and info.get("source") == curve_pda:
            sol_candidates.append(info)

    if not sol_candidates:
        return None
    best = max(sol_candidates, key=lambda i: i.get("lamports", 0))
    wallet = best.get("source") if is_buy else best.get("destination")

    return {
        "is_buy": is_buy,
        "wallet": wallet,
        "token_amount": int(token_amount_raw) / (10 ** decimals) if token_amount_raw else 0.0,
        "sol_amount": best.get("lamports", 0) / 1e9,
    }


def watch_pumpfun(mint, curve_pda, assoc_curve, rpc_url, interval, decimals, emit, stop_event, tr):
    emit("info", tr.t("log_watching_pumpfun", addr=curve_pda))
    seen = set()
    first_pass = True
    tick = 0

    while not stop_event.is_set():
        try:
            sigs = solana_get_signatures(rpc_url, curve_pda, limit=15)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            emit("error", tr.t("log_rpc_error", e=e, interval=interval))
            stop_event.wait(interval)
            continue

        for s in reversed(sigs):
            sig = s.get("signature")
            if sig in seen:
                continue
            seen.add(sig)
            if first_pass or s.get("err"):
                continue
            try:
                tx = solana_get_transaction(rpc_url, sig)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                continue

            trade = pumpfun_extract_trade(tx, curve_pda, assoc_curve, decimals)
            if not trade:
                continue
            ts = s.get("blockTime")
            ts_str = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "?"
            emit("trade", {
                "time": ts_str, "is_buy": trade["is_buy"], "wallet": trade["wallet"],
                "wallet_url": explorer_address_url("solana", trade["wallet"]),
                "amount": f"{trade['token_amount']:,.2f}", "amount_raw": trade["token_amount"],
                "quote_amount": f"{trade['sol_amount']:,.4f}", "quote_amount_raw": trade["sol_amount"],
                "quote_symbol": "SOL",
                "tx": sig, "tx_url": explorer_tx_url("solana", sig),
            })

        first_pass = False
        tick += 1
        if tick % 12 == 0:
            pf_info = fetch_pumpfun_info(mint)
            if pf_info and pf_info.get("complete"):
                emit("error", tr.t("log_pumpfun_migrated"))
                return

        stop_event.wait(interval)


# ---------------------------------------------------------------------------
# Solana (DEX-пулы после миграции)
# ---------------------------------------------------------------------------

def solana_get_signatures(rpc_url, address, limit=25):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
        "params": [address, {"limit": limit}],
    }
    return http_post_json(rpc_url, payload).get("result") or []


def solana_get_transaction(rpc_url, signature):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
    }
    return http_post_json(rpc_url, payload).get("result")


def solana_extract_buys(tx, mint, pool_owner_hint=None):
    if not tx or not tx.get("meta"):
        return []
    meta = tx["meta"]
    pre = {b["accountIndex"]: b for b in (meta.get("preTokenBalances") or []) if b.get("mint") == mint}
    post = {b["accountIndex"]: b for b in (meta.get("postTokenBalances") or []) if b.get("mint") == mint}

    buys = []
    for idx, post_bal in post.items():
        pre_bal = pre.get(idx)
        pre_amt = float(pre_bal["uiTokenAmount"]["uiAmountString"]) if pre_bal and pre_bal["uiTokenAmount"]["uiAmountString"] else 0.0
        post_amt = float(post_bal["uiTokenAmount"]["uiAmountString"]) if post_bal["uiTokenAmount"]["uiAmountString"] else 0.0
        delta = post_amt - pre_amt
        owner = post_bal.get("owner")
        if delta > 0 and owner and owner != pool_owner_hint:
            buys.append((owner, delta))
    return buys


def watch_solana(ca, pair_address, rpc_url, interval, emit, stop_event, tr):
    emit("info", tr.t("log_watching_solana", addr=pair_address))
    seen = set()
    first_pass = True

    while not stop_event.is_set():
        try:
            sigs = solana_get_signatures(rpc_url, pair_address, limit=15)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            emit("error", tr.t("log_rpc_error", e=e, interval=interval))
            stop_event.wait(interval)
            continue

        for s in reversed(sigs):
            sig = s.get("signature")
            if sig in seen:
                continue
            seen.add(sig)
            if first_pass or s.get("err"):
                continue
            try:
                tx = solana_get_transaction(rpc_url, sig)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                continue

            buys = solana_extract_buys(tx, ca, pool_owner_hint=pair_address)
            ts = s.get("blockTime")
            ts_str = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "?"
            for owner, amount in buys:
                emit("trade", {
                    "time": ts_str, "is_buy": True, "wallet": owner,
                    "wallet_url": explorer_address_url("solana", owner),
                    "amount": f"{amount:,.4f}", "amount_raw": amount,
                    "quote_amount": "", "quote_amount_raw": None, "quote_symbol": "",
                    "tx": sig, "tx_url": explorer_tx_url("solana", sig),
                })

        first_pass = False
        stop_event.wait(interval)


# ---------------------------------------------------------------------------
# EVM (Transfer-based, V2/V3-стиль пулов)
# ---------------------------------------------------------------------------

def evm_rpc_call(rpc_url, method, params):
    resp = http_post_json(rpc_url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "error" in resp:
        raise RuntimeError(resp["error"])
    return resp.get("result")


def evm_get_decimals(rpc_url, token_address):
    result = evm_rpc_call(rpc_url, "eth_call", [{"to": token_address, "data": "0x313ce567"}, "latest"])
    return int(result, 16) if result else 18


def evm_pad_address_topic(address):
    return "0x" + address.lower().replace("0x", "").rjust(64, "0")


def evm_topic_to_address(topic):
    return "0x" + topic[-40:]


def evm_word_signed(data_hex, index):
    raw = data_hex[2:] if data_hex.startswith("0x") else data_hex
    word = raw[index * 64:(index + 1) * 64]
    value = int(word, 16)
    if value >= (1 << 255):
        value -= (1 << 256)
    return value


def watch_evm(ca, chain_id, pair_address, rpc_url, interval, emit, stop_event, tr):
    emit("info", tr.t("log_watching_evm", addr=pair_address))
    try:
        decimals = evm_get_decimals(rpc_url, ca)
    except Exception:
        decimals = 18
    try:
        last_block = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
    except Exception as e:
        emit("error", tr.t("log_block_number_error", e=e))
        return

    pair_topic = evm_pad_address_topic(pair_address)

    while not stop_event.is_set():
        try:
            latest = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            emit("error", tr.t("log_rpc_error", e=e, interval=interval))
            stop_event.wait(interval)
            continue

        if latest > last_block:
            try:
                logs = evm_rpc_call(rpc_url, "eth_getLogs", [{
                    "address": ca, "topics": [TRANSFER_TOPIC],
                    "fromBlock": hex(last_block + 1), "toBlock": hex(latest),
                }])
            except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
                emit("error", tr.t("log_eth_getlogs_error", e=e, interval=interval))
                stop_event.wait(interval)
                continue

            for lg in logs or []:
                topics = lg.get("topics") or []
                if len(topics) < 3:
                    continue
                from_topic, to_topic = topics[1], topics[2]
                amount = int(lg.get("data", "0x0"), 16) / (10 ** decimals)
                if from_topic.lower() != pair_topic.lower():
                    continue
                buyer = evm_topic_to_address(to_topic)
                tx_hash = lg.get("transactionHash")
                emit("trade", {
                    "time": time.strftime("%H:%M:%S"), "is_buy": True, "wallet": buyer,
                    "wallet_url": explorer_address_url(chain_id, buyer),
                    "amount": f"{amount:,.4f}", "amount_raw": amount,
                    "quote_amount": "", "quote_amount_raw": None, "quote_symbol": "",
                    "tx": tx_hash, "tx_url": explorer_tx_url(chain_id, tx_hash),
                })

            last_block = latest
        stop_event.wait(interval)


def find_uniswap_v4_pool_manager(rpc_url, token_address, lookback_blocks=100000, max_checked=60):
    try:
        latest = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
        from_block = hex(max(0, latest - lookback_blocks))
        logs = evm_rpc_call(rpc_url, "eth_getLogs", [{
            "address": token_address, "topics": [TRANSFER_TOPIC],
            "fromBlock": from_block, "toBlock": "latest",
        }])
    except Exception:
        return None

    seen_tx = set()
    checked = 0
    for lg in reversed(logs or []):
        tx_hash = lg.get("transactionHash")
        if not tx_hash or tx_hash in seen_tx:
            continue
        seen_tx.add(tx_hash)
        if checked >= max_checked:
            break
        checked += 1
        try:
            receipt = evm_rpc_call(rpc_url, "eth_getTransactionReceipt", [tx_hash])
        except Exception:
            continue  # одиночный сбой RPC/rate-limit — пробуем следующую транзакцию
        for rl in (receipt or {}).get("logs", []):
            if rl.get("topics") and rl["topics"][0].lower() == UNISWAP_V4_SWAP_TOPIC.lower():
                return rl["address"]
    return None


def watch_evm_v4(ca, chain_id, pool_manager, pool_id, quote_token_address, quote_symbol,
                  rpc_url, interval, emit, stop_event, tr):
    emit("info", tr.t("log_watching_v4", addr=pool_id))
    emit("info", tr.t("log_poolmanager_label", addr=pool_manager))
    try:
        decimals = evm_get_decimals(rpc_url, ca)
    except Exception:
        decimals = 18
    is_native_quote = int(quote_token_address, 16) == 0
    if is_native_quote:
        quote_decimals = 18
    else:
        try:
            quote_decimals = evm_get_decimals(rpc_url, quote_token_address)
        except Exception:
            quote_decimals = 18
    is_token0 = int(ca, 16) < int(quote_token_address, 16)
    try:
        last_block = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
    except Exception as e:
        emit("error", tr.t("log_block_number_error", e=e))
        return

    while not stop_event.is_set():
        try:
            latest = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            emit("error", tr.t("log_rpc_error", e=e, interval=interval))
            stop_event.wait(interval)
            continue

        if latest > last_block:
            try:
                logs = evm_rpc_call(rpc_url, "eth_getLogs", [{
                    "address": pool_manager, "topics": [UNISWAP_V4_SWAP_TOPIC, pool_id],
                    "fromBlock": hex(last_block + 1), "toBlock": hex(latest),
                }])
            except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
                emit("error", tr.t("log_eth_getlogs_error", e=e, interval=interval))
                stop_event.wait(interval)
                continue

            for lg in logs or []:
                amount0 = evm_word_signed(lg["data"], 0)
                amount1 = evm_word_signed(lg["data"], 1)
                our_amount = amount0 if is_token0 else amount1
                quote_amount_raw = amount1 if is_token0 else amount0
                # Uniswap V4 (в отличие от V3!) использует знак с точки зрения трейдера:
                # positive = трейдер ПОЛУЧАЕТ этот токен из пула (покупка),
                # negative = трейдер ОТДАЁТ его в пул (продажа).
                is_buy = our_amount > 0
                token_amount = abs(our_amount) / (10 ** decimals)
                quote_amount = abs(quote_amount_raw) / (10 ** quote_decimals)

                wallet = "?"
                for _ in range(3):
                    try:
                        tx = evm_rpc_call(rpc_url, "eth_getTransactionByHash", [lg["transactionHash"]])
                        if tx and tx.get("from"):
                            wallet = tx["from"]
                        break
                    except Exception:
                        time.sleep(0.5)

                tx_hash = lg["transactionHash"]
                emit("trade", {
                    "time": time.strftime("%H:%M:%S"), "is_buy": is_buy, "wallet": wallet,
                    "wallet_url": explorer_address_url(chain_id, wallet),
                    "amount": f"{token_amount:,.4f}", "amount_raw": token_amount,
                    "quote_amount": f"{quote_amount:,.4f}", "quote_amount_raw": quote_amount,
                    "quote_symbol": quote_symbol,
                    "tx": tx_hash, "tx_url": explorer_tx_url(chain_id, tx_hash),
                })

            last_block = latest
        stop_event.wait(interval)


# ---------------------------------------------------------------------------
# Оркестратор
# ---------------------------------------------------------------------------

def run_watch(ca, interval, emit, stop_event, tr):
    ca = ca.strip()
    fmt = detect_chain_by_format(ca)
    if not fmt:
        emit("error", tr.t("log_invalid_ca"))
        return

    if fmt == "solana":
        emit("info", tr.t("log_checking_pumpfun", ca=ca))
        pf_info = fetch_pumpfun_info(ca)
        rpc_url = DEFAULT_SOLANA_RPC
        if pf_info and not pf_info.get("complete") and verify_pumpfun_curve(rpc_url, pf_info["bonding_curve"]):
            pf_decimals = pf_info.get("base_decimals", 6)
            mcap_anchor = pf_info.get("market_cap")
            price_native_anchor = None
            vsol = pf_info.get("virtual_sol_reserves")
            vtok = pf_info.get("virtual_token_reserves")
            if vsol and vtok:
                price_native_anchor = (vsol / 1e9) / (vtok / (10 ** pf_decimals))
            emit("meta", {
                "name": pf_info.get("name"), "symbol": pf_info.get("symbol"),
                "network": "Solana", "dex": tr.t("meta_source_pumpfun"),
                "price": "", "liquidity": f"{pf_info.get('market_cap', 0):,.2f} SOL (MC)",
                "mcap_anchor": mcap_anchor, "mcap_unit": " SOL", "mcap_unit_is_prefix": False,
                "price_native_anchor": price_native_anchor,
            })
            watch_pumpfun(ca, pf_info["bonding_curve"], pf_info["associated_bonding_curve"],
                          rpc_url, interval, pf_info.get("base_decimals", 6), emit, stop_event, tr)
            return

    emit("info", tr.t("log_checking_dexscreener"))
    try:
        info = fetch_dexscreener_info(ca)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        emit("error", tr.t("log_dexscreener_error", e=e))
        return

    if not info or not info.get("pairAddress"):
        emit("error", tr.t("log_no_pair"))
        return

    base = info["baseToken"]
    chain_id = (info.get("chainId") or "").lower()
    pair_address = info["pairAddress"]

    mcap_anchor = None
    price_native_anchor = None
    try:
        if info.get("marketCapUsd") and info.get("priceNative"):
            mcap_anchor = float(info["marketCapUsd"])
            price_native_anchor = float(info["priceNative"])
    except (TypeError, ValueError):
        pass

    emit("meta", {
        "name": base.get("name"), "symbol": base.get("symbol"),
        "network": info["chainId"], "dex": info["dexId"],
        "price": f"${info['priceUsd']}" if info.get("priceUsd") else "",
        "liquidity": f"${info['liquidityUsd']:,.0f}" if info.get("liquidityUsd") else "",
        "mcap_anchor": mcap_anchor, "mcap_unit": "$", "mcap_unit_is_prefix": True,
        "price_native_anchor": price_native_anchor,
    })

    if chain_id == "solana" or fmt == "solana":
        watch_solana(ca, pair_address, DEFAULT_SOLANA_RPC, interval, emit, stop_event, tr)
    elif fmt == "evm":
        rpc_url = DEFAULT_EVM_RPCS.get(chain_id, DEFAULT_EVM_RPCS["ethereum"])
        if len(pair_address) == 66:
            emit("info", tr.t("log_v4_detected", chain=chain_id))
            pool_manager = find_uniswap_v4_pool_manager(rpc_url, ca)
            if not pool_manager:
                emit("error", tr.t("log_v4_poolmanager_not_found"))
                return
            quote_address = info["quoteToken"].get("address")
            quote_symbol = info["quoteToken"].get("symbol") or ""
            watch_evm_v4(ca, chain_id, pool_manager, pair_address, quote_address, quote_symbol,
                         rpc_url, interval, emit, stop_event, tr)
        else:
            watch_evm(ca, chain_id, pair_address, rpc_url, interval, emit, stop_event, tr)
    else:
        emit("error", tr.t("log_unknown_chain", chain=chain_id))


# ---------------------------------------------------------------------------
# GUI — тёмная тема в стиле трейдинг-терминалов
# ---------------------------------------------------------------------------

BG = "#0a0c10"
PANEL = "#12151c"
PANEL2 = "#171b24"
BORDER = "#232733"
TEXT = "#e8e9ed"
MUTED = "#7d8493"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#9075ff"
GREEN = "#16c784"
GREEN_DIM = "#0f6b48"
RED = "#f6465d"
GOLD = "#ffb454"


def human_number(n):
    n = float(n)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1_000_000_000:
        return f"{sign}{n / 1_000_000_000:,.2f}B"
    if n >= 1_000_000:
        return f"{sign}{n / 1_000_000:,.2f}M"
    if n >= 1_000:
        return f"{sign}{n / 1_000:,.2f}K"
    return f"{sign}{n:,.2f}"


class App:
    def __init__(self, root):
        self.root = root
        self.tr = Translator("en")
        self.lang_var = tk.StringVar(value=LANG_NAMES["en"])

        root.title("XBIT888")
        root.geometry("1180x760")
        root.configure(bg=BG)
        root.minsize(980, 600)

        self._build_style()
        self._build_ui()

        self.log_queue = queue.Queue()
        self.stop_event = None
        self.worker = None
        self.meta_widgets = {}

        # живая статистика сессии
        self.buy_count = 0
        self.sell_count = 0
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.quote_symbol = ""
        self.price_history = []
        self.mcap_anchor = None
        self.mcap_unit = ""
        self.mcap_unit_is_prefix = True
        self.price_native_anchor = None
        self._live_on = False
        self._live_blink_state = True

        self.root.after(120, self.drain_queue)
        self.root.after(500, self._blink_live_dot)
        self.root.after(1000, self._tick_clock)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.retranslate()

    # -- style ---------------------------------------------------------
    def _build_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)

        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 9))
        style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 8))
        style.configure("PanelValue.TLabel", background=PANEL, foreground=TEXT, font=("Consolas", 11, "bold"))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 16, "bold"))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))

        style.configure("TEntry", fieldbackground=PANEL2, foreground=TEXT, insertcolor=TEXT,
                         bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=6)
        style.map("TEntry", fieldbackground=[("readonly", PANEL2)])

        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                         font=("Segoe UI", 10, "bold"), padding=(14, 8), borderwidth=0)
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("disabled", "#3a3550")],
                  foreground=[("disabled", "#8a86a0")])

        style.configure("Stop.TButton", background=PANEL2, foreground=RED,
                         font=("Segoe UI", 10, "bold"), padding=(14, 8), borderwidth=1)
        style.map("Stop.TButton", background=[("active", "#1e1420"), ("disabled", PANEL2)],
                  foreground=[("disabled", "#5a4247")])

        style.configure("Ghost.TButton", background=BG, foreground=MUTED,
                         font=("Segoe UI", 9), padding=(10, 6), borderwidth=1)
        style.map("Ghost.TButton", background=[("active", PANEL)], foreground=[("active", TEXT)])

        style.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=TEXT,
                         arrowcolor=TEXT, bordercolor=BORDER, padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL2)])

        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                         rowheight=26, font=("Consolas", 10), borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL2, foreground=MUTED,
                         font=("Segoe UI", 9, "bold"), borderwidth=0, relief="flat")
        style.map("Treeview.Heading", background=[("active", PANEL2)])
        style.map("Treeview", background=[("selected", "#221f33")], foreground=[("selected", TEXT)])

        style.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=BG, bordercolor=BG,
                         arrowcolor=MUTED)

    # -- layout ----------------------------------------------------------
    def _build_ui(self):
        # ---- header: бренд, live-индикатор, быстрая статистика ----
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=18, pady=(14, 6))

        brand_box = tk.Frame(header, bg=BG)
        brand_box.pack(side="left")
        brand_row = tk.Frame(brand_box, bg=BG)
        brand_row.pack(anchor="w")
        tk.Label(brand_row, text="XBIT", bg=BG, fg=TEXT, font=("Consolas", 20, "bold")).pack(side="left")
        tk.Label(brand_row, text="888", bg=BG, fg=GREEN, font=("Consolas", 20, "bold")).pack(side="left")
        self.subtitle_lbl = tk.Label(brand_box, bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.subtitle_lbl.pack(anchor="w")

        # live-индикатор по центру
        live_box = tk.Frame(header, bg=BG)
        live_box.pack(side="left", expand=True)
        live_inner = tk.Frame(live_box, bg=BG)
        live_inner.place(relx=0.5, rely=0.5, anchor="center")
        self.live_dot = tk.Canvas(live_inner, width=12, height=12, bg=BG, highlightthickness=0)
        self._live_dot_id = self.live_dot.create_oval(2, 2, 10, 10, fill=MUTED, outline="")
        self.live_dot.pack(side="left", padx=(0, 6))
        self.live_lbl = tk.Label(live_inner, bg=BG, fg=MUTED, font=("Consolas", 11, "bold"))
        self.live_lbl.pack(side="left")

        # быстрая статистика справа
        stats_box = tk.Frame(header, bg=BG)
        stats_box.pack(side="right")
        self.header_buys_cap, self.header_buys_val = self._header_stat(stats_box, GREEN)
        self.header_sells_cap, self.header_sells_val = self._header_stat(stats_box, RED)
        self.header_clock_cap, self.header_clock_val = self._header_stat(stats_box, TEXT, last=True)

        lang_box = tk.Frame(header, bg=BG)
        lang_box.pack(side="right", padx=(0, 22))
        self.lang_lbl = tk.Label(lang_box, bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.lang_lbl.pack(anchor="e")
        self.lang_combo = ttk.Combobox(lang_box, textvariable=self.lang_var, state="readonly",
                                        values=[LANG_NAMES[c] for c in LANGS], width=6, justify="center")
        self.lang_combo.pack(anchor="e", pady=(2, 0))
        self.lang_combo.bind("<<ComboboxSelected>>", self.on_lang_change)

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", padx=18)

        # ---- input row ----
        input_row = ttk.Frame(self.root, padding=(18, 10, 18, 10))
        input_row.pack(fill="x")

        ca_col = ttk.Frame(input_row)
        ca_col.pack(side="left", fill="x", expand=True)
        self.ca_label_lbl = ttk.Label(ca_col, style="Muted.TLabel")
        self.ca_label_lbl.pack(anchor="w")
        self.ca_entry = ttk.Entry(ca_col, font=("Consolas", 11))
        self.ca_entry.pack(fill="x", pady=(2, 0))
        self.ca_entry.bind("<Return>", lambda e: self.start())

        interval_col = ttk.Frame(input_row)
        interval_col.pack(side="left", padx=(12, 0))
        self.interval_label_lbl = ttk.Label(interval_col, style="Muted.TLabel")
        self.interval_label_lbl.pack(anchor="w")
        self.interval_var = tk.StringVar(value="1")
        ttk.Entry(interval_col, textvariable=self.interval_var, width=6, font=("Consolas", 11),
                  justify="center").pack(pady=(2, 0))

        btn_col = ttk.Frame(input_row)
        btn_col.pack(side="left", padx=(12, 0), anchor="s")
        self.start_btn = ttk.Button(btn_col, style="Accent.TButton", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(btn_col, style="Stop.TButton", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.clear_btn = ttk.Button(btn_col, style="Ghost.TButton", command=self.clear)
        self.clear_btn.pack(side="left")

        # ---- тело: три колонки ----
        body = ttk.Frame(self.root, padding=(18, 0, 18, 8))
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_token_card(body)
        self._build_feed_card(body)
        self._build_stats_card(body)

        # ---- панель логов ----
        log_frame = ttk.Frame(self.root, padding=(18, 0, 18, 6))
        log_frame.pack(fill="x")
        self.log_text = tk.Text(log_frame, height=4, bg=PANEL, fg=MUTED, insertbackground=TEXT,
                                 font=("Consolas", 9), relief="flat", wrap="word", state="disabled")
        self.log_text.pack(fill="x")
        self.log_text.tag_config("error", foreground=GOLD)
        self.log_text.tag_config("info", foreground=MUTED)

        # ---- статус-бар ----
        status_bar = ttk.Frame(self.root, padding=(18, 4, 18, 10))
        status_bar.pack(fill="x")
        self.status_var = tk.StringVar()
        ttk.Label(status_bar, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        self.hint_lbl = ttk.Label(status_bar, style="Muted.TLabel")
        self.hint_lbl.pack(side="right")

        self._row_count = 0
        self._row_data = {}  # iid -> {"wallet_url":..., "wallet":..., "tx_url":...}

    def _header_stat(self, parent, color, last=False):
        box = tk.Frame(parent, bg=BG)
        box.pack(side="left", padx=(0, 0) if last else (0, 22))
        cap = tk.Label(box, bg=BG, fg=MUTED, font=("Segoe UI", 8, "bold"))
        cap.pack(anchor="e")
        val = tk.Label(box, text="0", bg=BG, fg=color, font=("Consolas", 13, "bold"))
        val.pack(anchor="e")
        return cap, val

    def _card(self, parent, col, minwidth=None, weight=0):
        outer = tk.Frame(parent, bg=BORDER)
        outer.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 0 if col == 2 else 8))
        if minwidth:
            outer.grid_propagate(False)
            outer.configure(width=minwidth)
        parent.grid_columnconfigure(col, weight=weight)
        inner = tk.Frame(outer, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        return inner

    def _build_token_card(self, parent):
        card = self._card(parent, 0, minwidth=250)
        pad = tk.Frame(card, bg=PANEL, padx=14, pady=12)
        pad.pack(fill="both", expand=True)

        self.token_card_title = tk.Label(pad, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"))
        self.token_card_title.pack(anchor="w")

        id_row = tk.Frame(pad, bg=PANEL)
        id_row.pack(fill="x", pady=(10, 12))
        self.token_icon = tk.Label(id_row, text="?", width=3, bg=ACCENT, fg="#ffffff",
                                    font=("Segoe UI", 12, "bold"))
        self.token_icon.pack(side="left")
        name_box = tk.Frame(id_row, bg=PANEL)
        name_box.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.token_name_lbl = tk.Label(name_box, text="—", bg=PANEL, fg=TEXT,
                                        font=("Segoe UI", 12, "bold"), anchor="w")
        self.token_name_lbl.pack(fill="x")
        self.token_symbol_lbl = tk.Label(name_box, text="", bg=PANEL, fg=MUTED,
                                          font=("Segoe UI", 9), anchor="w")
        self.token_symbol_lbl.pack(fill="x")

        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=(0, 10))

        self.token_rows = {}
        for key, field in [("row_network", "network"), ("row_dex", "dex"),
                            ("row_price", "price"), ("row_liquidity", "liquidity")]:
            row = tk.Frame(pad, bg=PANEL)
            row.pack(fill="x", pady=4)
            cap = tk.Label(row, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w")
            cap.pack(anchor="w")
            val = tk.Label(row, text="—", bg=PANEL, fg=TEXT, font=("Consolas", 11, "bold"), anchor="w")
            val.pack(anchor="w")
            self.token_rows[field] = (key, cap, val)
        self.meta_labels = self.token_rows  # обратная совместимость с update_meta()

    def _build_feed_card(self, parent):
        card = self._card(parent, 1, weight=1)

        top = tk.Frame(card, bg=PANEL, padx=14, pady=12)
        top.pack(fill="x")
        left = tk.Frame(top, bg=PANEL)
        left.pack(side="left")
        self.feed_card_title = tk.Label(left, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"))
        self.feed_card_title.pack(anchor="w")
        right = tk.Frame(top, bg=PANEL)
        right.pack(side="right")
        self.last_price_cap = tk.Label(right, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="e")
        self.last_price_cap.pack(anchor="e")
        self.last_price_val = tk.Label(right, text="—", bg=PANEL, fg=GREEN,
                                        font=("Consolas", 16, "bold"), anchor="e")
        self.last_price_val.pack(anchor="e")

        self.spark_canvas = tk.Canvas(card, bg=PANEL, height=90, highlightthickness=0)
        self.spark_canvas.pack(fill="x", padx=14, pady=(0, 10))
        self.spark_placeholder = self.spark_canvas.create_text(
            10, 45, anchor="w", fill=MUTED, font=("Segoe UI", 9), text=""
        )
        self.spark_canvas.bind("<Configure>", lambda e: self._redraw_sparkline())

        table_frame = tk.Frame(card, bg=PANEL)
        table_frame.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        columns = ("time", "type", "wallet", "amount", "value", "tx")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", style="Treeview")
        for col, w, anchor in [
            ("time", 70, "center"), ("type", 100, "center"), ("wallet", 190, "w"),
            ("amount", 130, "e"), ("value", 110, "e"), ("tx", 170, "w"),
        ]:
            self.tree.column(col, width=w, anchor=anchor, stretch=(col in ("wallet", "tx")))
        self.tree.tag_configure("buy", foreground=GREEN, background="#0f2419")
        self.tree.tag_configure("sell", foreground=RED, background="#2a1116")
        self.tree.bind("<Double-Button-1>", self.on_row_double_click)
        self.tree.bind("<Motion>", self.on_row_hover)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    def _build_stats_card(self, parent):
        card = self._card(parent, 2, minwidth=220)
        pad = tk.Frame(card, bg=PANEL, padx=14, pady=12)
        pad.pack(fill="both", expand=True)

        self.stats_card_title = tk.Label(pad, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"))
        self.stats_card_title.pack(anchor="w")

        big_row = tk.Frame(pad, bg=PANEL)
        big_row.pack(fill="x", pady=(14, 10))

        buy_box = tk.Frame(big_row, bg=PANEL)
        buy_box.pack(side="left", expand=True, fill="x")
        self.stats_buys_val = tk.Label(buy_box, text="0", bg=PANEL, fg=GREEN, font=("Consolas", 26, "bold"))
        self.stats_buys_val.pack(anchor="w")
        self.stats_buys_cap = tk.Label(buy_box, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w")
        self.stats_buys_cap.pack(anchor="w")

        sell_box = tk.Frame(big_row, bg=PANEL)
        sell_box.pack(side="left", expand=True, fill="x")
        self.stats_sells_val = tk.Label(sell_box, text="0", bg=PANEL, fg=RED, font=("Consolas", 26, "bold"))
        self.stats_sells_val.pack(anchor="w")
        self.stats_sells_cap = tk.Label(sell_box, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w")
        self.stats_sells_cap.pack(anchor="w")

        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=(4, 10))

        self.stat_buy_vol_cap = tk.Label(pad, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w")
        self.stat_buy_vol_cap.pack(anchor="w")
        self.stat_buy_vol_val = tk.Label(pad, text="—", bg=PANEL, fg=GREEN, font=("Consolas", 12, "bold"), anchor="w")
        self.stat_buy_vol_val.pack(anchor="w", pady=(0, 8))

        self.stat_sell_vol_cap = tk.Label(pad, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w")
        self.stat_sell_vol_cap.pack(anchor="w")
        self.stat_sell_vol_val = tk.Label(pad, text="—", bg=PANEL, fg=RED, font=("Consolas", 12, "bold"), anchor="w")
        self.stat_sell_vol_val.pack(anchor="w", pady=(0, 8))

        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=(4, 10))

        self.stat_net_cap = tk.Label(pad, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w")
        self.stat_net_cap.pack(anchor="w")
        self.stat_net_val = tk.Label(pad, text="—", bg=PANEL, fg=TEXT, font=("Consolas", 15, "bold"), anchor="w")
        self.stat_net_val.pack(anchor="w")

    # -- i18n ------------------------------------------------------------
    def on_lang_change(self, _evt=None):
        code_by_name = {v: k for k, v in LANG_NAMES.items()}
        self.tr.lang = code_by_name.get(self.lang_var.get(), "ru")
        self.retranslate()

    def retranslate(self):
        t = self.tr.t
        self.root.title(t("app_title"))
        if not self.worker:
            self.subtitle_lbl.configure(text=t("app_subtitle"))
        self.lang_lbl.configure(text=t("lang_label"))
        self.ca_label_lbl.configure(text=t("ca_label"))
        self.interval_label_lbl.configure(text=t("interval_label"))
        self.start_btn.configure(text=t("start"))
        self.stop_btn.configure(text=t("stop"))
        self.clear_btn.configure(text=t("clear"))
        self.status_var.set(t("status_ready") if not self.worker else t("status_running"))

        self.live_lbl.configure(text=t("live") if self._live_on else t("offline"))
        self.header_buys_cap.configure(text=t("header_stat_buys"))
        self.header_sells_cap.configure(text=t("header_stat_sells"))
        self.header_clock_cap.configure(text=t("header_stat_clock"))

        self.token_card_title.configure(text=t("card_token_info"))
        self.feed_card_title.configure(text=t("card_live_feed"))
        self.stats_card_title.configure(text=t("card_live_stats"))
        self.last_price_cap.configure(text=t("last_price_label"))
        self.stats_buys_cap.configure(text=t("header_stat_buys"))
        self.stats_sells_cap.configure(text=t("header_stat_sells"))
        self.stat_buy_vol_cap.configure(text=t("stat_buy_volume"))
        self.stat_sell_vol_cap.configure(text=t("stat_sell_volume"))
        self.stat_net_cap.configure(text=t("stat_net_flow"))

        self.tree.heading("time", text=t("col_time"))
        self.tree.heading("type", text=t("col_type"))
        self.tree.heading("wallet", text=t("col_wallet"))
        self.tree.heading("amount", text=t("col_amount"))
        self.tree.heading("value", text=t("col_value"))
        self.tree.heading("tx", text=t("col_tx"))
        self.hint_lbl.configure(text=t("hint_click"))

        for field, (key, cap, val) in self.token_rows.items():
            cap.configure(text=t(key))

        if not self.price_history:
            self.spark_canvas.itemconfigure(self.spark_placeholder, text=t("no_chart_data"))

        # перевод уже вставленных строк типа BUY/SELL в таблице
        for row_id in self.tree.get_children():
            vals = list(self.tree.item(row_id, "values"))
            tags = self.tree.item(row_id, "tags")
            if "buy" in tags:
                vals[1] = "▲ " + t("trade_buy")
            elif "sell" in tags:
                vals[1] = "▼ " + t("trade_sell")
            self.tree.item(row_id, values=vals)

    # -- queue / events ----------------------------------------------------
    def emit(self, kind, payload):
        self.log_queue.put((kind, payload))

    def drain_queue(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "stopped":
                    self.start_btn.configure(state="normal")
                    self.ca_entry.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.status_var.set(self.tr.t("status_stopped"))
                    self._live_on = False
                    self.live_lbl.configure(text=self.tr.t("offline"))
                elif kind == "meta":
                    self.update_meta(payload)
                elif kind == "trade":
                    self.add_trade_row(payload)
                elif kind in ("info", "error"):
                    self.status_var.set(str(payload))
                    self.append_log(str(payload), kind)
        except queue.Empty:
            pass
        self.root.after(120, self.drain_queue)

    def append_log(self, text, tag):
        self.log_text.configure(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {text}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def update_meta(self, data):
        name = data.get("name") or ""
        symbol = data.get("symbol") or ""
        self.token_name_lbl.configure(text=name or "—")
        self.token_symbol_lbl.configure(text=symbol or "")
        self.token_icon.configure(text=(symbol or name or "?")[:1].upper())
        values = {
            "network": data.get("network") or "—",
            "dex": data.get("dex") or "—",
            "price": data.get("price") or "—",
            "liquidity": data.get("liquidity") or "—",
        }
        for field, (key, cap, val) in self.token_rows.items():
            val.configure(text=values.get(field, "—"))

        self.mcap_anchor = data.get("mcap_anchor")
        self.mcap_unit = data.get("mcap_unit") or ""
        self.mcap_unit_is_prefix = data.get("mcap_unit_is_prefix", True)
        self.price_native_anchor = data.get("price_native_anchor")

        # показываем капитализацию и стартовую точку графика сразу, не дожидаясь первой live-сделки
        if self.mcap_anchor:
            self.last_price_val.configure(text=self._format_mcap(self.mcap_anchor), fg=TEXT)
        if self.price_native_anchor and not self.price_history:
            self.price_history = [self.price_native_anchor]
            self._redraw_sparkline()

        parts = [p for p in [name, data.get("network"), data.get("dex")] if p]
        if parts:
            self.subtitle_lbl.configure(text="  ·  ".join(parts))

    def _format_mcap(self, value):
        text = human_number(value)
        return f"{self.mcap_unit}{text}" if self.mcap_unit_is_prefix else f"{text}{self.mcap_unit}"

    def add_trade_row(self, data):
        t = self.tr.t
        is_buy = data["is_buy"]
        tag_type = "buy" if is_buy else "sell"
        arrow = "▲" if is_buy else "▼"
        label = f"{arrow} " + (t("trade_buy") if is_buy else t("trade_sell"))
        self._row_count += 1

        wallet = data["wallet"]
        wallet_short = wallet if len(wallet) <= 20 else f"{wallet[:10]}…{wallet[-6:]}"
        tx_short = data["tx"] if len(data["tx"]) <= 22 else f"{data['tx'][:10]}…{data['tx'][-6:]}"
        quote_amount = data.get("quote_amount") or ""
        quote_symbol = data.get("quote_symbol") or ""
        value_text = f"{quote_amount} {quote_symbol}".strip() if quote_amount else "—"

        row_id = self.tree.insert(
            "", 0,
            values=(data["time"], label, wallet_short, data["amount"], value_text, tx_short),
            tags=(tag_type,),
        )
        self._row_data[row_id] = {
            "wallet": wallet,
            "wallet_url": data.get("wallet_url") or wallet,
            "tx_url": data.get("tx_url") or data["tx"],
        }

        # ограничиваем размер таблицы, чтобы GUI не разрастался бесконечно
        children = self.tree.get_children()
        if len(children) > 500:
            for old_id in children[500:]:
                self.tree.delete(old_id)
                self._row_data.pop(old_id, None)

        # -- живая статистика и график --
        amount_raw = data.get("amount_raw")
        quote_raw = data.get("quote_amount_raw")
        symbol = data.get("quote_symbol") or ""
        if symbol:
            self.quote_symbol = symbol

        if is_buy:
            self.buy_count += 1
            if quote_raw:
                self.buy_volume += quote_raw
        else:
            self.sell_count += 1
            if quote_raw:
                self.sell_volume += quote_raw

        self.header_buys_val.configure(text=f"{self.buy_count:,}")
        self.header_sells_val.configure(text=f"{self.sell_count:,}")
        self.stats_buys_val.configure(text=f"{self.buy_count:,}")
        self.stats_sells_val.configure(text=f"{self.sell_count:,}")

        if self.buy_volume or self.sell_volume:
            self.stat_buy_vol_val.configure(text=f"{self.buy_volume:,.4f} {self.quote_symbol}".strip())
            self.stat_sell_vol_val.configure(text=f"{self.sell_volume:,.4f} {self.quote_symbol}".strip())
            net = self.buy_volume - self.sell_volume
            net_color = GREEN if net >= 0 else RED
            sign = "+" if net >= 0 else ""
            self.stat_net_val.configure(text=f"{sign}{net:,.4f} {self.quote_symbol}".strip(), fg=net_color)

        if quote_raw and amount_raw:
            try:
                price = quote_raw / amount_raw
                self.price_history.append(price)
                if len(self.price_history) > 80:
                    self.price_history = self.price_history[-80:]
                if self.mcap_anchor and self.price_native_anchor:
                    ratio = price / self.price_native_anchor
                    live_mcap = self.mcap_anchor * ratio
                    self.last_price_val.configure(text=self._format_mcap(live_mcap),
                                                   fg=GREEN if is_buy else RED)
                else:
                    self.last_price_val.configure(text=f"{price:,.10f}".rstrip("0").rstrip("."),
                                                   fg=GREEN if is_buy else RED)
                self._redraw_sparkline()
            except ZeroDivisionError:
                pass

    def _redraw_sparkline(self):
        c = self.spark_canvas
        c.delete("spark")
        w = c.winfo_width() or 400
        h = c.winfo_height() or 90
        pts = self.price_history
        if len(pts) < 2:
            c.itemconfigure(self.spark_placeholder, text=self.tr.t("no_chart_data"))
            c.coords(self.spark_placeholder, 10, h // 2)
            return
        c.itemconfigure(self.spark_placeholder, text="")

        lo, hi = min(pts), max(pts)
        span = (hi - lo) or (hi * 0.01 or 1)
        pad = 6
        step = (w - 2 * pad) / (len(pts) - 1)

        def xy(i, v):
            x = pad + i * step
            y = h - pad - (v - lo) / span * (h - 2 * pad)
            return x, y

        for i in range(1, len(pts)):
            x0, y0 = xy(i - 1, pts[i - 1])
            x1, y1 = xy(i, pts[i])
            color = GREEN if pts[i] >= pts[i - 1] else RED
            c.create_line(x0, y0, x1, y1, fill=color, width=2, smooth=True, tags="spark")

        x1, y1 = xy(len(pts) - 1, pts[-1])
        last_color = GREEN if pts[-1] >= pts[-2] else RED
        c.create_oval(x1 - 3, y1 - 3, x1 + 3, y1 + 3, fill=last_color, outline="", tags="spark")

    def _blink_live_dot(self):
        if self._live_on:
            self._live_blink_state = not self._live_blink_state
            color = GREEN if self._live_blink_state else GREEN_DIM
            self.live_dot.itemconfigure(self._live_dot_id, fill=color)
            self.live_lbl.configure(fg=GREEN)
        else:
            self.live_dot.itemconfigure(self._live_dot_id, fill=MUTED)
            self.live_lbl.configure(fg=MUTED)
        self.root.after(600, self._blink_live_dot)

    def _tick_clock(self):
        self.header_clock_val.configure(text=time.strftime("%H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    def on_row_hover(self, event):
        region = self.tree.identify_region(event.x, event.y)
        col = self.tree.identify_column(event.x) if region == "cell" else None
        if col in ("#3", "#6"):  # wallet, tx
            self.tree.configure(cursor="hand2")
        else:
            self.tree.configure(cursor="")

    def on_row_double_click(self, event):
        row_id = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not row_id or row_id not in self._row_data:
            return
        info = self._row_data[row_id]
        if col == "#3":  # wallet
            self.root.clipboard_clear()
            self.root.clipboard_append(info["wallet"])
            self.status_var.set(self.tr.t("copied", value=info["wallet"]))
        elif col == "#6":  # tx
            webbrowser.open(info["tx_url"])

    # -- actions -----------------------------------------------------------
    def clear(self):
        for row_id in self.tree.get_children():
            self.tree.delete(row_id)
        self._row_count = 0
        self._row_data.clear()
        self.clear_log()

        self.buy_count = 0
        self.sell_count = 0
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.quote_symbol = ""
        self.price_history = []
        self.mcap_anchor = None
        self.mcap_unit = ""
        self.mcap_unit_is_prefix = True
        self.price_native_anchor = None
        self.header_buys_val.configure(text="0")
        self.header_sells_val.configure(text="0")
        self.stats_buys_val.configure(text="0")
        self.stats_sells_val.configure(text="0")
        self.stat_buy_vol_val.configure(text="—")
        self.stat_sell_vol_val.configure(text="—")
        self.stat_net_val.configure(text="—", fg=TEXT)
        self.last_price_val.configure(text="—", fg=GREEN)
        self._redraw_sparkline()

    def start(self):
        ca = self.ca_entry.get().strip()
        if not ca:
            self.status_var.set(self.tr.t("status_enter_ca"))
            return
        try:
            interval = max(0.5, float(self.interval_var.get()))
        except ValueError:
            interval = 1.0

        self.clear()
        for field, (key, cap, val) in self.token_rows.items():
            val.configure(text="—")
        self.token_name_lbl.configure(text="—")
        self.token_symbol_lbl.configure(text="")
        self.token_icon.configure(text="?")

        self.stop_event = threading.Event()
        self.start_btn.configure(state="disabled")
        self.ca_entry.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_var.set(self.tr.t("status_running"))
        self._live_on = True
        self.live_lbl.configure(text=self.tr.t("live"))

        tr = self.tr
        stop_event = self.stop_event

        def worker():
            try:
                run_watch(ca, interval, self.emit, stop_event, tr)
            except Exception as e:
                self.emit("error", tr.t("log_unexpected_error", e=e))
            finally:
                self.emit("stopped", None)

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def stop(self):
        if self.stop_event:
            self.stop_event.set()
        self.worker = None
        self._live_on = False
        self.live_lbl.configure(text=self.tr.t("offline"))
        self.status_var.set(self.tr.t("status_stopped"))
        self.start_btn.configure(state="normal")
        self.ca_entry.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def on_close(self):
        if self.stop_event:
            self.stop_event.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
