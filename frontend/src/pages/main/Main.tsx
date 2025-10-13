import {SongItem} from "./components/SongItem.tsx";
import {useServerSongs} from "./hooks/useServerSongs.ts";
import {useEffect} from "react";
import {usePlayer} from "../../context/PlayerContext.tsx";

function Main() {
    const {getSongs, songs} = useServerSongs()
    const {setPlaylist} = usePlayer()
    
    useEffect(() => {
        getSongs()
    }, [])
    
    useEffect(() => {
        if (songs && songs.length > 0) {
            setPlaylist(songs)
        }
    }, [songs, setPlaylist])
    
  return (
    <section className={'size-full'}>
        <h1 className={'text-neutral-100 text-3xl font-bold'}>Hecho para ti</h1>
      <div>
          <div className={'flex flex-wrap items-center w-full h-full gap-10 mt-20'}>
              {
                  songs && songs.map(song => 
                      <SongItem key={song.id} {...song} />
                  )
              }
          </div>
      </div>
    </section>
  )
}

export default Main
