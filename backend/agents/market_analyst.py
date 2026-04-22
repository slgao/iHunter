from groq import AsyncGroq
from agents.utils import parse_llm_json
from agents.config import MODEL


async def analyze_market(client: AsyncGroq, product_name: str, category: str, description: str) -> dict:
    prompt = f"""You are an expert in China-to-Germany export trade and the German market.

Analyze this Chinese product for the German market:
- Product: {product_name}
- Category: {category}
- Description: {description}

Return a JSON object with exactly these fields:
{{
  "market_fit_score": <integer 1-10>,
  "demand_level": "<low|medium|high>",
  "target_sectors": ["<sector1>", "<sector2>", "<sector3>"],
  "top_german_cities": ["<city1>", "<city2>", "<city3>"],
  "key_competitors": ["<competitor1>", "<competitor2>"],
  "import_considerations": "<brief note on EU/German import rules for this product>",
  "price_positioning": "<budget|mid-range|premium>",
  "b2b_potential": "<low|medium|high>",
  "b2c_potential": "<low|medium|high>",
  "market_insight": "<2-3 sentence insight about this product in the German market>"
}}

Return ONLY valid JSON, no markdown, no explanation."""

    response = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        temperature=0.7,
    )
    return parse_llm_json(response.choices[0].message.content)
