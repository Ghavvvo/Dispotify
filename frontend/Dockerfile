FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install -g pnpm
RUN pnpm install
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "run", "preview"]