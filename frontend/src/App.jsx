import React from 'react';
import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import Dashboard from './pages/dashboard/index.jsx';
import Highlights from './pages/highlights/index.jsx';
import { APP_NAME } from './constants/app.constants.js';


const router = createBrowserRouter([
  {
    path: '/',
    element: <Dashboard/>
  },
  {
    path: 'highlights/:streamId',
    element: <Highlights/>
  }
]);

function App(){
  document.title = APP_NAME
  return <RouterProvider router={router}/>
}

export default App;