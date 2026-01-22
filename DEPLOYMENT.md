# Spro Deal Withdrawal Bot - Koyeb Deployment

## Deploy to Koyeb

1. **Push your code to GitHub** (already done)

2. **Go to Koyeb Dashboard**: https://app.koyeb.com/

3. **Create New App**:
   - Click "Create App"
   - Select "Docker" as deployment method
   - Connect your GitHub repository: `xadarsh/Spro_Deal_Withdrawal_Bot`

4. **Configure Environment Variables**:
   Add these environment variables in Koyeb:
   - `API_ID` - Your Telegram API ID
   - `API_HASH` - Your Telegram API Hash
   - `BOT_TOKEN` - Your bot token from BotFather
   - `OWNER_ID` - Your Telegram user ID
   - `MONGO_URI` - Your MongoDB connection string
   - `MONGO_DB_NAME` - Your MongoDB database name

5. **Deploy Settings**:
   - Port: Not required (bot doesn't use web server)
   - Region: Choose nearest to you
   - Instance Type: Nano (free tier) should work fine

6. **Deploy**: Click "Deploy" and wait for the build to complete

## Local Testing with Docker

```bash
# Build the image
docker build -t spro-deal-bot .

# Run the container
docker run --env-file .env spro-deal-bot
```

## Notes
- The bot will automatically restart if it crashes (Koyeb handles this)
- Session files are stored in container (will reset on redeploy)
- Make sure MongoDB is accessible from Koyeb's servers
- TgCrypto is installed for better performance
