import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import {App} from "./App.tsx";
import { ToastContainer } from 'react-toastify';
import {BrowserRouter} from "react-router-dom";


createRoot(document.getElementById('root')!).render(
  <StrictMode>
      <BrowserRouter>
          <ToastContainer
              autoClose={5000}
              hideProgressBar={false}
              newestOnTop={false}
              closeOnClick
              rtl={false}
              pauseOnFocusLoss
              draggable
              pauseOnHover
              theme="dark"
          />

          <App /> 
      </BrowserRouter>
     
  </StrictMode>,
)
