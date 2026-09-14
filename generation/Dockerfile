FROM node:22-bookworm-slim
ARG CODEX_VERSION=0.154.0
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv git ca-certificates && rm -rf /var/lib/apt/lists/* \
    && npm install -g @openai/codex@${CODEX_VERSION}
WORKDIR /opt/browser
RUN npm init -y && npm install playwright@1.58.2 && npx playwright install --with-deps chromium
ENV NODE_PATH=/opt/browser/node_modules PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
RUN cp -a /root/.cache/ms-playwright /opt/browsers && chmod -R a+rX /opt/browsers
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
COPY generation/broker.py /opt/broker.py
RUN python3 -m venv /opt/planner && /opt/planner/bin/pip install --no-cache-dir openai-agents==0.8.4 openai==2.19.0
COPY generation/planner.py /opt/planner.py
USER node
WORKDIR /workspace
CMD ["sleep", "infinity"]
