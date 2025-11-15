import {Route, Routes} from "react-router-dom";
import {Layout} from "./components/common/Layout.tsx";
import Main from "./pages/main/Main.tsx";
import {UploadSong} from "./pages/upload-song/UploadSong.tsx";
import {PlayerProvider} from "./context/PlayerContext.tsx";
import {SearchProvider} from "./context/SearchContext.tsx";

export function App() {
    
    return (
        <PlayerProvider>
            <SearchProvider>
                <Layout>
                    <Routes>
                        <Route path={'/'} element={<Main />} />
                        <Route path={'/upload-song'} element={<UploadSong />} />
                    </Routes>
                </Layout>
            </SearchProvider>
        </PlayerProvider>
    )
}