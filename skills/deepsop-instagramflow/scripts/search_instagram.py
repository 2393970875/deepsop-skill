"""
Instagram Search Script (for deepsop-instagram skill)
Searches Instagram for influencers/daren by keyword via Apify API
"""
import os, sys, json, re

# Read API token from environment variable
API_TOKEN = os.environ.get("APIFY_TOKEN")
if not API_TOKEN:
    print("Error: APIFY_TOKEN environment variable not set!", file=sys.stderr)
    print("Get your token at https://console.apify.com/settings/integrations", file=sys.stderr)
    sys.exit(1)

os.environ["APIFY_TOKEN"] = API_TOKEN

# Force UTF-8 for stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from apify_client import ApifyClient
client = ApifyClient(API_TOKEN)

def strip_emoji(text):
    if not text:
        return text
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251"
        "\U0001F926-\U0001FA9F\u200d\u2640-\u2642\u2600-\u2B55\u23cf\u23e9"
        "\u231a\ufe0f\u3030\u2728\U00010000-\U0010ffff]+",
        flags=re.UNICODE)
    return emoji_pattern.sub('', text)

def search_instagram(keyword, max_results=20):
    """Search Instagram by keyword"""
    search_input = {"search": keyword, "searchType": "user", "maxResults": max_results}
    print(f"\nSearching '{keyword}' ...")

    run = client.actor("apify/instagram-search-scraper").call(run_input=search_input)

    print(f"  Status: {run.status}")
    if run.status != "SUCCEEDED":
        raise Exception(f"Run failed: {run.status_message}")

    items = list(client.dataset(run.default_dataset_id).iterate_items())
    print(f"  Got {len(items)} results")
    return items

def format_results(items):
    if not items:
        return []

    results = []
    for i, item in enumerate(items, 1):
        entry = item.get("entry", item)

        username = entry.get("username") or ""
        full_name = entry.get("fullName") or ""
        bio = entry.get("biography") or ""
        followers = entry.get("followersCount") or 0
        following = entry.get("followsCount") or 0
        posts = entry.get("postsCount") or 0
        verified = entry.get("verified") or False
        is_business = entry.get("isBusinessAccount") or False
        category = entry.get("businessCategoryName") or ""
        is_private = entry.get("private") or False
        profile_pic = entry.get("profilePicUrl") or ""
        external_url = entry.get("externalUrls", [None])[0] if entry.get("externalUrls") else ""
        related_profiles = entry.get("relatedProfiles", [])[:5]

        if not username:
            continue

        results.append({
            "no": i,
            "username": f"@{username}",
            "name": strip_emoji(full_name or ""),
            "followers": followers,
            "following": following,
            "posts": posts,
            "verified": verified,
            "business": is_business,
            "private": is_private,
            "category": category,
            "bio": strip_emoji(bio[:150] + "..." if bio and len(bio) > 150 else (bio or "")),
            "external_url": external_url or "",
            "profile_pic": profile_pic or "",
            "profile_url": f"https://instagram.com/{username}",
            "related_profiles": related_profiles,
        })

    return results

def main():
    if len(sys.argv) < 2:
        print("Usage: python search_instagram.py <keyword> [max_results]")
        sys.exit(1)

    keyword = sys.argv[1]
    max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    try:
        items = search_instagram(keyword, max_results)
        results = format_results(items)

        # Save data
        with open("apify_output.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        with open("apify_output_raw.json", "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

        if not results:
            print("\n  No user results found.")
            return

        # Print table
        print(f"\n{'='*140}")
        print(f"  Instagram Search Results: '{keyword}' ({len(results)} profiles)")
        print(f"{'='*140}")
        print(f"  {'#':<3} {'Username':<24} {'Followers':<12} {'Posts':<7} {'V':<2} {'Name':<22} {'Category':<20} Bio")
        print(f"  {'-'*135}")

        for r in results:
            v = "Y" if r["verified"] else " "
            f_count = f"{r['followers']:,}" if isinstance(r['followers'], (int, float)) and r['followers'] else "?"
            p_count = r["posts"] if r["posts"] else "?"
            n = r["name"][:20] if r["name"] else "-"
            c = r["category"][:18] if r["category"] else "-"
            b_text = r["bio"][:55] if r["bio"] else "-"
            print(f"  {r['no']:<3} {r['username']:<24} {str(f_count):<12} {str(p_count):<7} {v:<2} {n:<22} {c:<20} {b_text}")

        # Cost estimate
        est_cost = len(results) * 0.0023
        print(f"\n  Cost: ~${est_cost:.4f} USD ($2.30/1k results)")
        print(f"  Data saved to apify_output.json")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
