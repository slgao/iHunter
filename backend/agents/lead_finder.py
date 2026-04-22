from groq import AsyncGroq
from agents.utils import parse_llm_json
from agents.config import MODEL


BATCH_SIZE = 10


async def _fetch_b2b_batch(client, product_name, category, description, target_sectors, top_cities, count) -> list:
    city_instruction = f"ONLY use these cities: {', '.join(top_cities)}." if top_cities else "Use major German cities."
    prompt = f"""You are a B2B lead generation expert for the German market.

Generate {count} realistic German B2B company leads that would import or resell this Chinese product:
- Product: {product_name}
- Category: {category}
- Description: {description}
- Target Sectors: {', '.join(target_sectors)}
- Cities: {city_instruction}

Return a JSON array of {count} objects, each with:
{{
  "company_name": "<real-sounding German company name>",
  "contact_name": "<realistic German full name>",
  "email": "<professional email based on company name>",
  "phone": "<German phone format +49...>",
  "city": "<German city>",
  "industry": "<specific industry>",
  "description": "<1 sentence why this company would want the product>",
  "type": "b2b"
}}

Use realistic German names, cities (Hamburg, Munich, Berlin, Frankfurt, Düsseldorf, Stuttgart, Cologne, etc.).
Return ONLY a valid JSON array, no markdown."""

    response = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
        temperature=0.8,
    )
    return parse_llm_json(response.choices[0].message.content)


async def find_b2b_leads(
    client: AsyncGroq,
    product_name: str,
    category: str,
    description: str,
    target_sectors: list,
    top_cities: list,
    count: int = 8,
) -> list:
    results = []
    remaining = count
    while remaining > 0:
        batch = min(remaining, BATCH_SIZE)
        leads = await _fetch_b2b_batch(client, product_name, category, description, target_sectors, top_cities, batch)
        results.extend(leads)
        remaining -= batch
    return results


async def _fetch_b2c_batch(client, product_name, category, description, cities, count) -> list:
    city_instruction = f"Only use these cities: {', '.join(cities)}." if cities else "Use major German cities."
    prompt = f"""You are a B2C customer research expert for the German market.

Generate {count} realistic German individual customer profiles who would buy this Chinese product:
- Product: {product_name}
- Category: {category}
- Description: {description}
- Cities: {city_instruction}

Return a JSON array of {count} objects, each with:
{{
  "contact_name": "<realistic German full name>",
  "email": "<personal email, gmail.com/web.de/gmx.de/t-online.de>",
  "phone": "<German mobile +49 15x/16x/17x>",
  "city": "<German city from the list above>",
  "description": "<1 sentence persona — age, lifestyle, why they'd buy>",
  "type": "b2c"
}}

Return ONLY a valid JSON array, no markdown."""

    response = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        temperature=0.8,
    )
    return parse_llm_json(response.choices[0].message.content)


async def find_b2c_leads(
    client: AsyncGroq,
    product_name: str,
    category: str,
    description: str,
    count: int = 6,
    cities: list = None,
) -> list:
    results = []
    remaining = count
    while remaining > 0:
        batch = min(remaining, BATCH_SIZE)
        leads = await _fetch_b2c_batch(client, product_name, category, description, cities or [], batch)
        results.extend(leads)
        remaining -= batch
    return results
