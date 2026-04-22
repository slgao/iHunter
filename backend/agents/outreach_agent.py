from groq import AsyncGroq
from agents.utils import parse_llm_json
from agents.config import MODEL


async def generate_outreach(
    client: AsyncGroq,
    lead: dict,
    product_name: str,
    product_description: str,
    price_range: str,
    moq: str,
    origin_city: str,
) -> dict:
    lead_type = lead.get("type", "b2b")
    recipient = lead.get("company_name") or lead.get("contact_name")
    contact = lead.get("contact_name", "")
    city = lead.get("city", "Germany")
    industry = lead.get("industry", "")
    persona = lead.get("description", "")

    if lead_type == "b2b":
        context = f"Company: {recipient}, Contact: {contact}, City: {city}, Industry: {industry}, Background: {persona}"
        tone = "professional, B2B trade tone"
        cta_de = "Wären Sie an einem unverbindlichen Beratungsgespräch interessiert?"
        cta_en = "Would you be open to a no-obligation consultation call?"
    else:
        context = f"Individual customer: {contact}, City: {city}, Profile: {persona}"
        tone = "friendly, consumer-focused tone"
        cta_de = "Möchten Sie mehr erfahren oder eine Probe bestellen?"
        cta_en = "Would you like to learn more or request a sample?"

    prompt = f"""You are a professional sales copywriter for cross-border trade (China to Germany).

Write a personalized cold outreach email for this lead about our Chinese product.

PRODUCT:
- Name: {product_name}
- Description: {product_description}
- Price range: {price_range}
- MOQ: {moq}
- Ships from: {origin_city}, China

RECIPIENT:
- {context}

Write in {tone}.
Keep each email concise: 100-130 words max.

IMPORTANT JSON rules:
- Use \\n for line breaks inside strings — do NOT use actual newlines
- All four fields must be complete before closing the object

Return ONLY a JSON object with no text before or after:
{{
  "subject_de": "<German subject line>",
  "subject_en": "<English subject line>",
  "body_de": "<German body using \\n for line breaks, ending with: {cta_de}>",
  "body_en": "<English body using \\n for line breaks, ending with: {cta_en}>"
}}"""

    response = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        temperature=0.7,
    )
    return parse_llm_json(response.choices[0].message.content)
