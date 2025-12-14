FROM node:18-alpine

WORKDIR /app

RUN npm install -g pnpm

COPY package.json ./
RUN pnpm install --prod

COPY server.js ./

EXPOSE 3000

CMD ["node", "server.js"]