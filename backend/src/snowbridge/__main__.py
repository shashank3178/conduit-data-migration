"""Run the local Snowbridge API: python -m snowbridge."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("snowbridge.api:app", host="127.0.0.1", port=8000, reload=True)
