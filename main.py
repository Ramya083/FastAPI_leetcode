from fastapi import FastAPI, HTTPException
import httpx

app = FastAPI()

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

QUERY = """
query getUserProfile($username: String!) {
  matchedUser(username: $username) {
    username
    profile {
      realName
      ranking
      userAvatar
      reputation
    }
    submitStats {
      acSubmissionNum {
        difficulty
        count
      }
    }
  }
}
"""

@app.get("/leetcode/{username}")
async def get_leetcode_stats(username: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            LEETCODE_GRAPHQL_URL,
            json={"query": QUERY, "variables": {"username": username}},
            headers={"Content-Type": "application/json"}
        )
    
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch data from LeetCode")

    data = response.json()
    user_data = data.get("data", {}).get("matchedUser")

    if not user_data:
        raise HTTPException(status_code=404, detail="LeetCode user not found")

    profile = user_data["profile"]
    submissions = user_data["submitStats"]["acSubmissionNum"]

    stats = {
        "username": user_data["username"],
        "real_name": profile["realName"],
        "ranking": profile["ranking"],
        "reputation": profile["reputation"],
        "avatar": profile["userAvatar"],
        "solved": {
            "total": next((x["count"] for x in submissions if x["difficulty"] == "All"), 0),
            "easy": next((x["count"] for x in submissions if x["difficulty"] == "Easy"), 0),
            "medium": next((x["count"] for x in submissions if x["difficulty"] == "Medium"), 0),
            "hard": next((x["count"] for x in submissions if x["difficulty"] == "Hard"), 0),
        }
    }

    return stats