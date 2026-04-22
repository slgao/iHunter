from groq import AsyncGroq
from agents.utils import parse_llm_json
from agents.config import MODEL


async def suggest_real_companies(
    client: AsyncGroq,
    product_name: str,
    category: str,
    description: str,
    cities: list,
    count: int = 15,
    exclude: list[str] | None = None,
) -> list:
    city_clause = f"Focus on these cities: {', '.join(cities)}." if cities else "Spread across major German cities."

    exclude_clause = ""
    if exclude:
        # Keep only unique values, cap at 40 to limit token use
        unique = list(dict.fromkeys(e for e in exclude if e))[:40]
        listed = ", ".join(unique)
        exclude_clause = f"\nSkip these already-known companies: {listed}\n"

    prompt = f"""You are an expert in the German B2B market and cross-border trade.

Suggest {count} REAL, EXISTING German companies that are the BEST FIT for this product:
- Product: {product_name}
- Category: {category}
- Description: {description}
- {city_clause}
{exclude_clause}
Ranking criteria (most important first):
1. Product relevance — the company's core business directly matches this product's category or use case
2. Likelihood to import or buy from China — active importers, distributors, or online shops that source internationally
3. Realistic fit — their price point, customer base, and assortment would naturally include this product

Size does NOT matter — a highly relevant small specialist beats a large irrelevant retailer.
Mix types freely: importers, wholesalers, specialist retailers, online shops, distributors, Amazon FBA sellers.

Rules:
- Only suggest companies that ACTUALLY EXIST with a REAL, WORKING website
- DO NOT include email addresses — leave email discovery to the web scraper
- If unsure whether a company is real, skip it and replace with a more relevant one
- Return results sorted by relevance score descending

Return a JSON array of {count} objects:
{{
  "company_name": "<exact real company name>",
  "website": "<actual domain only, e.g. thomann.de — NO https://, NO email>",
  "city": "<city where headquartered>",
  "industry": "<specific industry/niche>",
  "reason": "<1 sentence specifically explaining why THIS product fits THEIR business>",
  "size": "<small|medium|large>",
  "type": "<retailer|wholesaler|distributor|online_shop|amazon_seller|importer>"
}}

Return ONLY a valid JSON array, no markdown."""

    response = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2500,
        temperature=0.2,
    )
    return parse_llm_json(response.choices[0].message.content)
