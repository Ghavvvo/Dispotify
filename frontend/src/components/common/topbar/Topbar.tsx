import { useNavigate } from "react-router-dom";
import { Search, Upload, Filter, X } from "lucide-react";
import { useState, useEffect, useRef } from "react";
import { useSearchContext } from "../../../context/SearchContext";

export function Topbar() {
    const navigate = useNavigate();
    const { performSearch, clearSearch, activeFilters } = useSearchContext();
    const [showFilters, setShowFilters] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [filters, setFilters] = useState({
        genero: "",
        autor: "",
        album: "",
    });
    const filterRef = useRef<HTMLDivElement>(null);

    // Cerrar el menú de filtros al hacer clic fuera
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (filterRef.current && !filterRef.current.contains(event.target as Node)) {
                setShowFilters(false);
            }
        };

        if (showFilters) {
            document.addEventListener("mousedown", handleClickOutside);
        }

        return () => {
            document.removeEventListener("mousedown", handleClickOutside);
        };
    }, [showFilters]);

    const handleSearch = () => {
        const searchFilters = {
            q: searchQuery,
            ...filters,
        };
        performSearch(searchFilters);
    };

    const handleClearSearch = () => {
        setSearchQuery("");
        setFilters({
            genero: "",
            autor: "",
            album: "",
        });
        clearSearch();
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === "Enter") {
            handleSearch();
        }
    };

    const hasActiveFilters = searchQuery || filters.genero || filters.autor || filters.album;

    return (
        <header className={'flex w-full h-24 items-center justify-center px-4 py-3 bg-black relative'}>
            <div 
                className={'hover:cursor-pointer flex items-center gap-4 absolute left-4 top-1/2 transform -translate-y-1/2'}
                onClick={() => navigate("/") }
            >
                <img src={'/spotify.png'} alt={'spotify'} className={'w-12 h-12'} />
                <h2 className={'text-[#40B26B] text-2xl font-bold'}>Dispotify</h2>
            </div>
            
            <div className={'relative w-1/3 h-full flex items-center gap-2'}>
                <div className={'relative flex-1 h-full'}>
                    <input
                        className={'w-full h-full rounded-full bg-[#1F1F1F] placeholder:text-neutral-100/50 text-neutral-100 px-4 pl-14 pr-10'}
                        placeholder={'¿Qué quieres reproducir?'}
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyPress={handleKeyPress}
                    />
                    <Search 
                        className={'absolute left-4 top-1/2 transform -translate-y-1/2 text-neutral-100/50 w-6 h-6 cursor-pointer hover:text-neutral-100 transition-colors'} 
                        onClick={handleSearch}
                    />
                    {hasActiveFilters && (
                        <X 
                            className={'absolute right-4 top-1/2 transform -translate-y-1/2 text-neutral-100/50 w-5 h-5 cursor-pointer hover:text-neutral-100 transition-colors'} 
                            onClick={handleClearSearch}
                        />
                    )}
                </div>
                
                <div className={'relative'} ref={filterRef}>
                    <button
                        className={`h-12 px-4 rounded-full flex items-center gap-2 transition-all ${
                            showFilters || Object.values(filters).some(f => f)
                                ? 'bg-[#40B26B] text-white'
                                : 'bg-[#1F1F1F] text-neutral-100/50 hover:text-neutral-100'
                        }`}
                        onClick={() => setShowFilters(!showFilters)}
                    >
                        <Filter className={'w-5 h-5'} />
                        <span className={'text-sm font-medium'}>Filtros</span>
                    </button>

                    {showFilters && (
                        <div className={'absolute top-full mt-2 right-0 bg-[#1F1F1F] rounded-lg p-4 shadow-xl z-50 w-72'}>
                            <h3 className={'text-neutral-100 font-semibold mb-3'}>Filtrar por:</h3>
                            
                            <div className={'space-y-3'}>
                                <div>
                                    <label className={'text-neutral-100/70 text-sm mb-1 block'}>Género</label>
                                    <input
                                        type="text"
                                        className={'w-full bg-[#121212] text-neutral-100 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#40B26B]'}
                                        placeholder={'Ej: Rock, Pop, Jazz...'}
                                        value={filters.genero}
                                        onChange={(e) => setFilters({ ...filters, genero: e.target.value })}
                                        onKeyPress={handleKeyPress}
                                    />
                                </div>

                                <div>
                                    <label className={'text-neutral-100/70 text-sm mb-1 block'}>Autor</label>
                                    <input
                                        type="text"
                                        className={'w-full bg-[#121212] text-neutral-100 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#40B26B]'}
                                        placeholder={'Nombre del artista'}
                                        value={filters.autor}
                                        onChange={(e) => setFilters({ ...filters, autor: e.target.value })}
                                        onKeyPress={handleKeyPress}
                                    />
                                </div>

                                <div>
                                    <label className={'text-neutral-100/70 text-sm mb-1 block'}>Álbum</label>
                                    <input
                                        type="text"
                                        className={'w-full bg-[#121212] text-neutral-100 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#40B26B]'}
                                        placeholder={'Nombre del álbum'}
                                        value={filters.album}
                                        onChange={(e) => setFilters({ ...filters, album: e.target.value })}
                                        onKeyPress={handleKeyPress}
                                    />
                                </div>
                            </div>

                            <div className={'flex gap-2 mt-4'}>
                                <button
                                    className={'flex-1 bg-[#40B26B] text-white rounded-md px-4 py-2 text-sm font-medium hover:bg-[#35a05d] transition-colors'}
                                    onClick={() => {
                                        handleSearch();
                                        setShowFilters(false);
                                    }}
                                >
                                    Aplicar
                                </button>
                                <button
                                    className={'flex-1 bg-[#121212] text-neutral-100 rounded-md px-4 py-2 text-sm font-medium hover:bg-[#2a2a2a] transition-colors'}
                                    onClick={() => {
                                        setFilters({ genero: "", autor: "", album: "" });
                                    }}
                                >
                                    Limpiar
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </div>
            
            <button className={'flex gap-4 hover:from-green-500 transition-all hover:cursor-pointer absolute right-4 top-1/2 transform -translate-y-1/2 bg-white rounded-lg px-4 py-2 font-semibold bg-gradient-to-r from-green-400 to-green-500'}
                onClick={() => {
                    navigate("upload-song")
                }}
            >
                Subir canción
                <Upload width={18} strokeWidth={2}/>
            </button>
        </header>
    )
}
