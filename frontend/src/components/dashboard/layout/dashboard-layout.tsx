import Link from 'next/link';
import Image from 'next/image';
import { ReactNode } from 'react';
import { DashboardGradient } from '@/components/gradients/dashboard-gradient';
import '../../../styles/dashboard.css';
import { Sidebar } from '@/components/dashboard/layout/sidebar';
import { SidebarUserInfo } from '@/components/dashboard/layout/sidebar-user-info';

interface Props {
  children: ReactNode;
}

export function DashboardLayout({ children }: Props) {
  return (
    <div className="flex h-screen w-full relative overflow-hidden">
      <DashboardGradient />

      {/* Fixed Sidebar */}
      <div className="hidden border-r md:flex md:w-[220px] lg:w-[280px] relative flex-col">
        <div className="flex items-center pt-8 pl-6 pb-10">
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <Image src={'/assets/icons/logo/veridex-logo-icon.svg'} alt={'Veridex'} width={41} height={41} />
          </Link>
        </div>
        <div className="flex flex-col flex-1 min-h-0">
          <Sidebar />
          <SidebarUserInfo />
        </div>
      </div>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto">{children}</div>
    </div>
  );
}
