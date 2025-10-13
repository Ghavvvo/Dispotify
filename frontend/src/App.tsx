import {Route, Routes} from "react-router-dom";
import {Layout} from "./components/common/Layout.tsx";
import Main from "./pages/main/Main.tsx";
import {UploadSong} from "./pages/upload-song/UploadSong.tsx";
import {PlayerProvider} from "./context/PlayerContext.tsx";
import {VolumeIndicator} from "./components/VolumeIndicator.tsx";

export function App() {
    
    return (
        <PlayerProvider>
            <VolumeIndicator />
            <Layout>
                <Routes>
                    <Route path={'/'} element={<Main />} />
                    <Route path={'/upload-song'} element={<UploadSong />} />
                </Routes>
            </Layout>
        </PlayerProvider>
    )
}