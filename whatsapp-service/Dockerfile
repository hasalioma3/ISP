# Build stage: git is required by npm to resolve some of Baileys'
# transitive dependencies (fetched straight from a repo, not the npm
# registry) -- needed to install, not to run, so it stays out of the final
# image.
FROM node:20-alpine AS deps

RUN apk add --no-cache git

WORKDIR /app

# npm ci installs exactly what package-lock.json pins -- plain npm install
# against package.json alone re-resolved Baileys' ^range on every build, so
# the Pi could silently pick up a different WhatsApp protocol client.
COPY package.json package-lock.json /app/
RUN npm ci --omit=dev

FROM node:20-alpine

WORKDIR /app

# Heap cap keeps a leak or a runaway sync from eating the Pi's RAM;
# restart: always brings the service back if it's ever hit.
ENV NODE_ENV=production
ENV NODE_OPTIONS=--max-old-space-size=256

COPY --from=deps /app/node_modules /app/node_modules
COPY package.json index.js /app/

RUN mkdir -p /app/auth

CMD ["node", "index.js"]
