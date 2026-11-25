"use client";

import { CircleDollarSign, GraduationCap, LayoutDashboard, Upload, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { routes } from "@/lib/routes";

/** The left navigation. Collapses to icons with ⌘B or its edge; on a phone it slides over the page. */
export function AppSidebar() {
  const pathname = usePathname();
  const { isMobile, setOpenMobile } = useSidebar();
  // On a phone the sidebar covers the page: close it once a link is chosen.
  const closeSidebarOnMobile = () => isMobile && setOpenMobile(false);

  return (
    <Sidebar variant="floating" collapsible="icon">
      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu className="gap-1">
            <SidebarMenuItem>
              <SidebarMenuButton
                className="h-10 rounded-xl"
                isActive={pathname === routes.executive}
                tooltip="Executive"
                render={<Link href={routes.executive} onClick={closeSidebarOnMobile} />}
              >
                <LayoutDashboard />
                <span>Executive</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton
                className="h-10 rounded-xl"
                isActive={pathname === routes.studentServices}
                tooltip="Student services"
                render={<Link href={routes.studentServices} onClick={closeSidebarOnMobile} />}
              >
                <Users />
                <span>Student services</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton
                className="h-10 rounded-xl"
                isActive={pathname === routes.academic}
                tooltip="Academic hold"
                render={<Link href={routes.academic} onClick={closeSidebarOnMobile} />}
              >
                <GraduationCap />
                <span>Academic hold</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton
                className="h-10 rounded-xl"
                isActive={pathname === routes.financial}
                tooltip="Financial hold"
                render={<Link href={routes.financial} onClick={closeSidebarOnMobile} />}
              >
                <CircleDollarSign />
                <span>Financial hold</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton
                className="h-10 rounded-xl"
                isActive={pathname === routes.upload}
                tooltip="Upload"
                render={<Link href={routes.upload} onClick={closeSidebarOnMobile} />}
              >
                <Upload />
                <span>Upload</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  );
}
