FROM node:20-alpine

# git is required by npm to resolve some of Baileys' transitive
# dependencies (fetched straight from a repo, not the npm registry) --
# Alpine's base image doesn't include it.
RUN apk add --no-cache git

WORKDIR /app

COPY package.json /app/
RUN npm install --omit=dev

COPY index.js /app/

RUN mkdir -p /app/auth

CMD ["node", "index.js"]
