import os
import json
import re
from datetime import datetime
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import anthropic

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "SEU_TOKEN_AQUI")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "SUA_CHAVE_ANTHROPIC_AQUI")

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

DATA_FILE = "gastos.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_month_key():
    return datetime.now().strftime("%Y-%m")

def get_month_label():
    months = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho",
               "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]
    now = datetime.now()
    return f"{months[now.month - 1]} {now.year}"

def parse_expense_with_ai(text: str) -> dict | None:
    system = """Você é um assistente que extrai informações de gastos pessoais de mensagens em português.

Dado um texto, extraia:
- valor: número decimal (ex: 45.90)
- categoria: uma das opções: mercado, alimentacao, transporte, saude, lazer, casa, vestuario, outros
- descricao: descrição curta do gasto (máx 30 chars)

Responda APENAS com JSON válido, sem texto adicional. Exemplo:
{"valor": 45.90, "categoria": "alimentacao", "descricao": "Almoço restaurante"}

Se não for um gasto, responda: {"erro": "nao_e_gasto"}"""

    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=150,
        system=system,
        messages=[{"role": "user", "content": text}]
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    return json.loads(raw)

CATEGORY_EMOJI = {
    "mercado": "🛒", "alimentacao": "🍽️", "transporte": "🚗",
    "saude": "💪", "lazer": "🎬", "casa": "🏠",
    "vestuario": "👕", "outros": "📦"
}
CATEGORY_LABEL = {
    "mercado": "Mercado", "alimentacao": "Alimentação", "transporte": "Transporte",
    "saude": "Saúde", "lazer": "Lazer", "casa": "Casa",
    "vestuario": "Vestuário", "outros": "Outros"
}

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 *Assistente Financeiro Pessoal*\n\n"
        "Manda seus gastos em linguagem natural:\n\n"
        "  • _Mercado R\\$180_\n"
        "  • _Almoço 45 reais_\n"
        "  • _Uber 22_\n"
        "  • _Paguei 120 na academia_\n\n"
        "*Comandos:*\n"
        "/resumo — gastos do mês\n"
        "/historico — todos os meses\n"
        "/ajuda — instruções",
        parse_mode="MarkdownV2"
    )

async def resumo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load_data()
    month = get_month_key()
    user_data = data.get(uid, {}).get(month, [])

    if not user_data:
        await update.message.reply_text(f"Nenhum gasto em {get_month_label()} ainda. Comece enviando um gasto! 😊")
        return

    by_cat = defaultdict(float)
    for g in user_data:
        by_cat[g["categoria"]] += g["valor"]

    total = sum(by_cat.values())
    lines = [f"📊 *{get_month_label()}* — {len(user_data)} lançamentos\n"]
    for cat, val in sorted(by_cat.items(), key=lambda x: -x[1]):
        emoji = CATEGORY_EMOJI.get(cat, "📦")
        label = CATEGORY_LABEL.get(cat, cat)
        lines.append(f"{emoji} {label}: R\\$ {val:.2f}".replace(".", ","))

    lines.append(f"\n💰 *Total: R\\$ {total:.2f}*".replace(".", ","))
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")

async def historico(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load_data()
    user_data = data.get(uid, {})

    if not user_data:
        await update.message.reply_text("Nenhum gasto registrado ainda.")
        return

    months_pt = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    lines = ["📅 *Histórico de gastos:*\n"]
    for month in sorted(user_data.keys(), reverse=True):
        gastos = user_data[month]
        total = sum(g["valor"] for g in gastos)
        y, m = month.split("-")
        label = f"{months_pt[int(m)-1]}/{y}"
        lines.append(f"• {label}: R\\$ {total:.2f} \\({len(gastos)} gastos\\)".replace(".", ","))

    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")

async def ajuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Como usar:*\n\n"
        "Mande qualquer mensagem descrevendo um gasto\\. A IA vai entender automaticamente\\.\n\n"
        "*Exemplos:*\n"
        "• Mercado 180\n"
        "• Almocei fora, gastei 55 reais\n"
        "• Paguei a academia 120\n"
        "• Combustível 200\n\n"
        "*Comandos:*\n"
        "/resumo — resumo do mês atual\n"
        "/historico — histórico de todos os meses\n"
        "/start — recomeçar",
        parse_mode="MarkdownV2"
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    text = update.message.text

    await update.message.chat.send_action("typing")

    try:
        result = parse_expense_with_ai(text)
    except Exception as e:
        await update.message.reply_text("Erro ao processar. Tente novamente.")
        return

    if "erro" in result:
        await update.message.reply_text(
            "Não entendi como um gasto 🤔\n"
            "Tente algo como: _Mercado R$120_ ou _Almoço 45 reais_\n\n"
            "Use /ajuda para ver exemplos.",
            parse_mode="Markdown"
        )
        return

    valor = result["valor"]
    cat = result.get("categoria", "outros")
    desc = result.get("descricao", text[:30])
    emoji = CATEGORY_EMOJI.get(cat, "📦")
    label = CATEGORY_LABEL.get(cat, cat)

    data = load_data()
    month = get_month_key()
    if uid not in data:
        data[uid] = {}
    if month not in data[uid]:
        data[uid][month] = []

    data[uid][month].append({
        "valor": valor, "categoria": cat,
        "descricao": desc, "data": datetime.now().isoformat()
    })
    save_data(data)

    total_mes = sum(g["valor"] for g in data[uid][month])
    await update.message.reply_text(
        f"{emoji} *Registrado\\!*\n"
        f"{label}: R\\$ {valor:.2f}\n"
        f"_{desc}_\n\n"
        f"Total em {get_month_label()}: *R\\$ {total_mes:.2f}*".replace(".", ","),
        parse_mode="MarkdownV2"
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resumo", resumo))
    app.add_handler(CommandHandler("historico", historico))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot rodando...")
    app.run_polling()

if __name__ == "__main__":
    main()
