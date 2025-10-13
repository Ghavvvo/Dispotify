import type {ReactNode} from "react";
import {Topbar} from "./topbar/Topbar.tsx";
import {Footer} from "./footer/Footer.tsx";
import {useKeyboardShortcuts} from "../../hooks/useKeyboardShortcuts.ts";

export function Layout({children}: {children: ReactNode}) {
    useKeyboardShortcuts();
    
    return (
        <div className={'flex flex-col h-dvh'}>
            <Topbar />
            <div className={'bg-neutral-900 size-full p-10  overflow-y-auto scrollbar-thin'}>
                {children}
            </div>
            <Footer />
        </div>
    )
}