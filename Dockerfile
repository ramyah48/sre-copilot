FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the MCP server over stdio so it can be attached as a
# plugin. Override with `docker run <image> python demo.py` to run the
# backtest instead.
CMD ["python", "-m", "argus.server"]
