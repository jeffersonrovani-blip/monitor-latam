#!/usr/bin/env python3
"""Monitor de cotacoes finais LATAM: sem simular preco nem contornar bloqueios."""
import argparse
import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
DATA = Path(os.getenv('MONITOR_DATA_DIR', str(ROOT)))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'historico.sqlite3'
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def brl_to_cents(value):
    if isinstance(value, str):
        value = value.strip().replace('R$', '').replace('BRL', '').replace(' ', '')
        if ',' in value:
            value = value.replace('.', '').replace(',', '.')
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Preco invalido') from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError('Preco deve ser positivo')
    return int((amount * 100).quantize(Decimal('1')))


def setup(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS cotacoes (
        id INTEGER PRIMARY KEY, consultado_em TEXT NOT NULL,
        preco_centavos INTEGER NOT NULL, fonte TEXT NOT NULL,
        url TEXT, confirmado INTEGER NOT NULL, observacao TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS alertas (
        id INTEGER PRIMARY KEY, cotacao_id INTEGER NOT NULL,
        enviado_em TEXT NOT NULL, preco_centavos INTEGER NOT NULL)''')
    conn.commit()


def send_telegram(message):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        logging.warning('Telegram nao configurado; alerta nao enviado.')
        return False
    req = Request(f'https://api.telegram.org/bot{token}/sendMessage',
                  data=urlencode({'chat_id': chat, 'text': message}).encode(), method='POST')
    with urlopen(req, timeout=20) as response:
        answer = json.load(response)
    if not answer.get('ok'):
        raise RuntimeError('Telegram nao confirmou a mensagem')
    return True


def save_quote(price, source, url='', confirmed=False, observation=''):
    cents = brl_to_cents(price)
    with sqlite3.connect(DB) as conn:
        setup(conn)
        cursor = conn.execute('INSERT INTO cotacoes (consultado_em,preco_centavos,fonte,url,confirmado,observacao) VALUES (?,?,?,?,?,?)',
                              (now(), cents, source, url, int(confirmed), observation))
        quote_id = cursor.lastrowid
        conn.commit()
        limit = brl_to_cents(CFG['preco_maximo_brl'])
        if not confirmed:
            logging.info('Cotacao indicativa R$ %.2f; SEM alerta de compra.', cents / 100)
            return
        logging.info('Cotacao confirmada R$ %.2f | meta R$ %.2f', cents / 100, limit / 100)
        if cents > limit:
            return
        # Evita repeticao da mesma faixa de preco; reenvia quando atingir novo minimo.
        prev = conn.execute('SELECT MIN(preco_centavos) FROM alertas').fetchone()[0]
        if prev is not None and cents >= prev:
            logging.info('Alerta ja enviado para preco igual ou menor.')
            return
        msg = (f'LATAM GRU ⇄ IMP | 1 adulto\n'
               f'Ida: {CFG["ida"]} | Volta: {CFG["volta"]}\n'
               f'Preco final: R$ {cents / 100:,.2f}\n'
               f'Meta: R$ {limit / 100:,.2f}\n'
               f'Fonte: {source}\n{url}\n'
               'Verifique novamente a disponibilidade antes de comprar.')
        if send_telegram(msg):
            conn.execute('INSERT INTO alertas (cotacao_id,enviado_em,preco_centavos) VALUES (?,?,?)', (quote_id, now(), cents))
            conn.commit()


def browser_capture(url, visible=False, save_only=False):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit('Instale: pip install playwright && python -m playwright install chromium') from exc
    if not url.startswith('https://') or 'latamairlines.com' not in url.split('/')[2].lower():
        raise SystemExit('Use uma URL HTTPS do dominio latamairlines.com')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not visible)
        context = browser.new_context(locale='pt-BR', timezone_id='America/Sao_Paulo')
        page = context.new_page()
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(7000)
            if visible:
                print('Navegue ate o resumo final de 1 passageiro, ida e volta, Light.')
                input('Quando estiver no resumo final, pressione ENTER aqui... ')
            text = page.locator('body').inner_text(timeout=15000)
            (DATA / 'ultima_pagina.txt').write_text(text, encoding='utf-8')
            page.screenshot(path=str(DATA / 'ultima_pagina.png'), full_page=True)
            # Apenas sugestao. Nao trata preco por trecho como preco final.
            matches = re.findall(r'(?:Subtotal|Total\s*(?:da viagem)?)[\s\S]{0,100}?(?:BRL|R\$)\s*([\d.,]+)', text, re.I)
            print('Valores possivelmente totais:', matches or 'nenhum detectado')
            print('Captura salva: ultima_pagina.txt e ultima_pagina.png')
            if matches and not save_only:
                print('Confira visualmente passageiros, datas, bagagem, taxas e valor final.')
                answer = input('Informe o PRECO FINAL confirmado (ex.: 2.959,51), ou ENTER para nao registrar: ').strip()
                if answer:
                    save_quote(answer, 'latam_site_confirmacao_humana', page.url, True,
                               'Confirmado visualmente pelo operador; nao e coleta automatica validada')
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description='Monitor LATAM GRU/IMP')
    sub = parser.add_subparsers(dest='command', required=True)
    manual = sub.add_parser('registrar', help='Registra preco final conferido manualmente')
    manual.add_argument('--preco', required=True)
    manual.add_argument('--url', default='')
    manual.add_argument('--confirmado', action='store_true', help='Voos, bagagem, impostos e 1 passageiro conferidos')
    browser = sub.add_parser('capturar', help='Captura experimental de pagina LATAM')
    browser.add_argument('--url', required=True)
    browser.add_argument('--visivel', action='store_true')
    browser.add_argument('--somente-captura', action='store_true')
    sub.add_parser('status', help='Mostra historico')
    args = parser.parse_args()
    if args.command == 'registrar':
        save_quote(args.preco, 'latam_manual' if args.confirmado else 'indicativa_manual', args.url, args.confirmado)
    elif args.command == 'capturar':
        browser_capture(args.url, args.visivel, args.somente_captura)
    else:
        with sqlite3.connect(DB) as conn:
            setup(conn)
            for row in conn.execute('SELECT consultado_em, preco_centavos, fonte, confirmado FROM cotacoes ORDER BY id DESC LIMIT 15'):
                print(f'{row[0]} | R$ {row[1]/100:.2f} | {row[2]} | confirmado={bool(row[3])}')


if __name__ == '__main__':
    main()
