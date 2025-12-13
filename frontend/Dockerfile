FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install -g pnpm
RUN pnpm install
COPY . .

# Variables de entorno para la API
ARG VITE_API_URL
ARG VITE_STATIC_URL

ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_STATIC_URL=${VITE_STATIC_URL}

EXPOSE 3000
CMD ["pnpm", "run", "dev", "--host", "0.0.0.0", "--port", "3000"]
