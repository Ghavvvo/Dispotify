import {SongItem} from "./components/SongItem.tsx";
import {useServerSongs} from "./hooks/useServerSongs.ts";
import {useEffect} from "react";
import {useSearchContext} from "../../context/SearchContext.tsx";

function Main() {
    const {getSongs, songs} = useServerSongs()
    const {searchResults, activeFilters} = useSearchContext()
    
    useEffect(() => {
        getSongs()
    }, [])
    
    // Determinar qué canciones mostrar: resultados de búsqueda o todas las canciones
    const displaySongs = Object.keys(activeFilters).some(key => activeFilters[key as keyof typeof activeFilters]) 
        ? searchResults 
        : songs;
    
    const hasActiveSearch = Object.keys(activeFilters).some(key => activeFilters[key as keyof typeof activeFilters]);
    
  return (
    <section className={'size-full'}>
        <h1 className={'text-neutral-100 text-3xl font-bold'}>
            {hasActiveSearch ? 'Resultados de búsqueda' : 'Hecho para ti'}
        </h1>
      <div>
          <div className={'flex flex-wrap items-center w-full h-full gap-10 mt-20'}>
              {
                  displaySongs && displaySongs.length > 0 ? (
                      displaySongs.map(song => 
                          <SongItem key={song.id} {...song} />
                      )
                  ) : hasActiveSearch ? (
                      <p className={'text-neutral-100/50 text-lg'}>
                          No se encontraron canciones con los filtros aplicados
                      </p>
                  ) : null
              }
          </div>
      </div>
    </section>
  )
}

export default Main
