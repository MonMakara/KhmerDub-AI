FROM node:20-alpine

# Install system dependencies including timezone data
RUN apk add --no-cache tzdata

WORKDIR /app

# Install dependencies first for Docker caching
COPY package*.json ./
RUN npm install

# Copy application files
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
