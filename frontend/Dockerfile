FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install -g pnpm
RUN pnpm install
COPY . .

# Variable de entorno para la API
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

EXPOSE 3000
CMD ["pnpm", "run", "dev", "--host", "0.0.0.0", "--port", "3000"]
