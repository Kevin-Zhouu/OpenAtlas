FROM node:22-bookworm-slim
ARG CODEX_VERSION=0.154.0
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv git ca-certificates && rm -rf /var/lib/apt/lists/* \
    && npm install -g @openai/codex@${CODEX_VERSION}
WORKDIR /opt/browser
RUN npm init -y && npm install playwright@1.58.2 && npx playwright install --with-deps chromium
ENV NODE_PATH=/opt/browser/node_modules PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
RUN cp -a /root/.cache/ms-playwright /opt/browsers && chmod -R a+rX /opt/browsers
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
RUN python3 -m venv /opt/planner && /opt/planner/bin/pip install --no-cache-dir openai-agents==0.8.4 openai==2.19.0
# Matching server/addon from an immutable upstream revision. Blender uses a
# private software-rendered display; no desktop display or GPU is mounted.
ARG BLENDER_MCP_REVISION=5f8ddaf6e987c4aa0c3467fcc548838b28f64477
RUN apt-get update && apt-get install -y --no-install-recommends blender xvfb xauth python3-requests libgl1-mesa-dri \
    && rm -rf /var/lib/apt/lists/* \
    && git clone https://github.com/ahujasid/blender-mcp.git /opt/blender-mcp-source \
    && cd /opt/blender-mcp-source && git checkout "$BLENDER_MCP_REVISION" \
    && python3 -m venv /opt/blender-mcp \
    && /opt/blender-mcp/bin/pip install --no-cache-dir . mcp==1.29.0 httpx==0.28.1 \
    && rm -rf /opt/blender-mcp-source/.git
# Debian recommends (rather than requires) NumPy; GLB export and screenshots need it.
RUN apt-get update && apt-get install -y --no-install-recommends python3-numpy && rm -rf /var/lib/apt/lists/*
ENV BLENDER_MCP_DISABLE_TELEMETRY=1 LIBGL_ALWAYS_SOFTWARE=1
COPY generation/blender_startup.py generation/blender_mcp.py generation/blender_server.py /opt/
COPY generation/broker.py generation/planner.py generation/subscription_model.py generation/subscription_login.py /opt/
USER node
WORKDIR /workspace
CMD ["sleep", "infinity"]
