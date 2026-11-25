# Deploy your own

The dashboard is two Vercel projects, one for the API and one for the web app, deployed with the
[Vercel CLI](https://vercel.com/docs/cli) from a clone of this repo. Use your own Vercel account;
nothing here points at one.

**1. API project**

1. Create a Vercel project. In its settings, set **Root Directory** to
   `playground/server_application` and turn on **Include files outside the root directory**. The
   framework preset is FastAPI.
2. Add these production environment variables. Every setting is listed in
   [`playground/server_application/.env.example`](../playground/server_application/.env.example).

   | Variable | Value |
   | --- | --- |
   | `APP_ENV` | `production` |
   | `DATABASE_URL` | `sqlite:////tmp/playground.db` (the dashboard doesn't need a real database) |
   | `DASHBOARD_DATA_DIR` | `synthetic-datasets` |
   | `CORS_ORIGINS` | `["https://<your-web-app>.vercel.app"]` |

3. From the **repo root**, link and deploy. The root [`.vercelignore`](../.vercelignore) keeps the
   upload small.

   ```bash
   vercel link --project <your-api-project>
   vercel deploy --prod
   ```

4. Check it: `https://<your-api>.vercel.app/api/v1/health` returns `"status": "ok"`.

**2. Web project**

1. Create a second Vercel project with the Next.js preset and an empty **Root Directory**.
2. Add production environment variables `NEXT_PUBLIC_APP_ENV=production` and
   `NEXT_PUBLIC_API_BASE_URL=https://<your-api>.vercel.app/api/v1`.
3. Deploy from the web app's folder:

   ```bash
   cd playground/client_application
   vercel link --project <your-web-project>
   vercel deploy --prod
   ```

4. Open `https://<your-web-app>.vercel.app/dashboard`. Set the API's `CORS_ORIGINS` to this address
   if you hadn't yet, and redeploy the API.

Uploads on Vercel are saved to `/tmp` and are lost when the service restarts. The hosted site has
no sign-in, so don't upload real student records to it; run it locally for those.
