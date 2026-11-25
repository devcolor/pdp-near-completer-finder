import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { ThemeProvider } from "@/components/theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { brand } from "@/content/brand";
import { cn } from "@/lib/utils";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  // The browser tab is the tool name. A page can still set its own title.
  title: { default: "Near Completers Tool", template: "%s · Near Completers Tool" },
  description: brand.tagline,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // next-themes sets the theme class on <html> before React hydrates.
    <html lang="en" className={cn("font-sans antialiased", inter.variable)} suppressHydrationWarning>
      <body>
        <style>{`
          @media print {
            @page { margin: 0.6in; size: letter; }
            html {
              --background: #fff !important;
              --foreground: #111 !important;
              --card: #fff !important;
              --card-foreground: #111 !important;
              --muted-foreground: #444 !important;
              --border: #ccc !important;
              color-scheme: light !important;
              background: #fff !important;
            }
            html, body,
            [data-slot="sidebar-wrapper"],
            [data-slot="sidebar-inset"],
            [data-slot="resizable-panel-group"],
            [data-slot="resizable-panel"],
            .h-svh {
              height: auto !important;
              max-height: none !important;
              overflow: visible !important;
              background: #fff !important;
              color: #111 !important;
            }
            .overflow-hidden, .overflow-y-auto {
              overflow: visible !important;
            }
            /* Beats an older print rule that painted every bar white and locked the accent to Copper Mountain teal. */
            .h-2 { height: 0.5rem !important; }
            .h-full { height: 100% !important; }
            .bg-brand { background-color: var(--brand) !important; }
            .bg-muted { background-color: var(--muted) !important; }
            * {
              print-color-adjust: exact !important;
              -webkit-print-color-adjust: exact !important;
            }
            [data-slot="sidebar"],
            [data-slot="sidebar-gap"],
            [data-slot="sidebar-container"],
            [data-slot="sidebar-rail"],
            .no-print,
            nextjs-portal {
              display: none !important;
            }
          }
        `}</style>
        <ThemeProvider>
          <TooltipProvider>{children}</TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
