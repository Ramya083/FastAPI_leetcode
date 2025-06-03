from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
import pandas as pd
import requests
import re
import io
import time

app = FastAPI(title="LeetCode Ranker API")

# -----------------------
# Utility functions
# -----------------------

def extract_username_from_url(url):
    match = re.search(r"leetcode\.com/u/([a-zA-Z0-9_\-]+)/?", str(url))
    return match.group(1) if match else None

def fetch_user_data(username):
    url = "https://leetcode.com/graphql"
    query = """
    query getUserProfile($username: String!) {
        matchedUser(username: $username) {
            submitStats {
                acSubmissionNum {
                    difficulty
                    count
                }
            }
        }
    }
    """
    variables = {"username": username}
    headers = {
        "Content-Type": "application/json",
        "Referer": f"https://leetcode.com/u/{username}/",
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.post(url, json={"query": query, "variables": variables}, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            stats = data.get("data", {}).get("matchedUser", {}).get("submitStats", {}).get("acSubmissionNum", [])
            if not stats:
                return None
            difficulties = {"Easy": 0, "Medium": 0, "Hard": 0}
            total = 0
            for item in stats:
                difficulty = item.get("difficulty", "")
                count = item.get("count", 0)
                if difficulty in difficulties:
                    difficulties[difficulty] = count
                    total += count
            return {
                "totalSolved": total,
                "easySolved": difficulties["Easy"],
                "mediumSolved": difficulties["Medium"],
                "hardSolved": difficulties["Hard"],
            }
    except Exception:
        return None
    return None

def fetch_user_data_with_retries(username, retries=3, delay=1):
    for _ in range(retries):
        data = fetch_user_data(username)
        if data:
            return data
        time.sleep(delay)
    return None

# -----------------------
# Processing Logic
# -----------------------

def process_file(file: UploadFile):
    try:
        df_input = pd.read_excel(file.file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading Excel file: {e}")

    url_col = None
    for col in df_input.columns:
        if df_input[col].astype(str).str.contains(r"leetcode\.com/u/", regex=True).any():
            url_col = col
            break

    if not url_col:
        raise HTTPException(status_code=400, detail="No column found with LeetCode profile URLs.")

    results = []
    failed_users = []

    for url in df_input[url_col].dropna():
        url = str(url).strip()
        username = extract_username_from_url(url)

        if not username:
            failed_users.append((url, "Invalid URL"))
            continue

        data = fetch_user_data_with_retries(username, retries=3, delay=2)

        if data:
            results.append({
                "username": username,
                "profile_url": url,
                **data
            })
        else:
            failed_users.append((username, "API failed"))
            results.append({
                "username": username,
                "profile_url": url,
                "totalSolved": "N/A",
                "easySolved": "N/A",
                "mediumSolved": "N/A",
                "hardSolved": "N/A"
            })

    df_result = pd.DataFrame(results)

    df_numeric = df_result[df_result['totalSolved'] != "N/A"].copy()
    df_numeric["totalSolved"] = pd.to_numeric(df_numeric["totalSolved"])
    df_numeric["Rank"] = df_numeric["totalSolved"].rank(method="min", ascending=False).astype(int)

    df_final = pd.merge(df_result, df_numeric[["username", "Rank"]], on="username", how="left")
    df_final = df_final.sort_values(by="Rank", na_position="last")

    return df_final, failed_users

# -----------------------
# API Endpoints
# -----------------------

@app.post("/rank")
async def rank_users(
    file: UploadFile = File(...),
    output_format: str = Query("json", enum=["json", "excel"])
):
    """
    Upload an Excel file with LeetCode profile URLs.
    Returns ranked user data in JSON or downloadable Excel format.
    """
    df_final, failed_users = process_file(file)

    if output_format == "excel":
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df_final.to_excel(writer, index=False, sheet_name="LeetCode Rankings")
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=leetcode_rankings.xlsx"}
        )
    else:
        return JSONResponse({
            "rankings": df_final.to_dict(orient="records"),
            "failed": failed_users
        })
