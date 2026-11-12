# シエルの体（マイクラの Java 版に入るボット。会話モデルは使わない）。docs/minecraft-design-ja.md
# 目（src/eye.js）のために、画面の無い Chromium（Playwright の headless shell）を入れる。docs/minecraft-vision-design-ja.md
FROM node:22.23.3-bookworm-slim

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev \
 && npx playwright install --with-deps --only-shell chromium \
 && rm -rf /var/lib/apt/lists/* /root/.npm
COPY src/ ./src/
RUN mkdir -p /app/bots && chown node:node /app/bots

USER node
CMD ["node", "src/main.js"]
