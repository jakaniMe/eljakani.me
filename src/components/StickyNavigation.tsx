import React, { useState, useEffect, useRef } from 'react';
import {
  FlaskConical,
  BriefcaseBusiness,
  BookOpen,
  Mic,
  Trophy,
  GraduationCap,
  Sprout,
  type LucideIcon,
} from 'lucide-react';

import { Button } from '@/components/ui/button';

const icons: Record<string, LucideIcon> = {
  FlaskConical,
  BriefcaseBusiness,
  BookOpen,
  Mic,
  Trophy,
  GraduationCap,
  Sprout,
};

interface NavItem {
  id: string;
  label: string;
  icon: string;
}
interface StickyNavigationProps {
  navItems: NavItem[];
}

const StickyNavigation: React.FC<StickyNavigationProps> = ({ navItems }) => {
  const [activeSection, setActiveSection] = useState(navItems[0]?.id ?? 'research');
  const [isSticky, setIsSticky] = useState(false);
  const prevScrollY = useRef(0);
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      setIsSticky(currentScrollY > 100);
      prevScrollY.current = currentScrollY;
    };

    window.addEventListener('scroll', handleScroll, { passive: true });

    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    const observerOptions = {
      root: null,
      rootMargin: '-20% 0px -80% 0px',
      threshold: 0,
    };

    const observerCallback: IntersectionObserverCallback = (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          setActiveSection(entry.target.id);
        }
      });
    };

    const observer = new IntersectionObserver(observerCallback, observerOptions);

    navItems.forEach((item) => {
      const element = document.getElementById(item.id.toLowerCase());
      if (element) observer.observe(element);
    });

    return () => observer.disconnect();
  }, [navItems]);

  return (
    <nav
      ref={navRef}
      className={`sticky-nav ${isSticky ? 'sticky-nav--sticky' : ''}`}
    >
      <div className="bg-muted rounded-full container mx-auto flex justify-between items-center p-1 md:p-2 px-1.5 md:px-3 border">
        <div className="flex justify-between gap-1 md:gap-2">
          {navItems.map((item) => {
            const IconComponent = icons[item.icon];
            return (
              <Button
                key={item.id}
                aria-label={item.label}
                variant={activeSection === item.id.toLowerCase() ? 'default' : 'ghost'}
                size="sm"
                className="rounded-full flex items-center gap-1 md:gap-2"
                onClick={() => {
                  const element = document.getElementById(item.id.toLowerCase());
                  if (element) {
                    element.scrollIntoView({ behavior: 'smooth' });
                  }
                }}
              >
                {IconComponent && <IconComponent size={20} />}
                <span className="text-sm hidden xl:block">{item.label}</span>
              </Button>
            );
          })}
        </div>
        <div className="text-end p-1 font-alt hidden md:block">
          <span className="text-lg font-bold whitespace-nowrap">Y. El Jakani<span className="text-point">.</span></span>
        </div>
      </div>
    </nav>
  );
};

export default StickyNavigation;
