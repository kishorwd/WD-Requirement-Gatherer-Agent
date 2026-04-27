import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ProjectProvider } from './context/ProjectContext';
import Sidebar from './components/Sidebar';
import PreMeeting from './pages/PreMeeting';
import PostMeeting from './pages/PostMeeting';
import ScopeGap from './pages/ScopeGap';
import UserStories from './pages/UserStories';
import './styles/index.css';
import './styles/components.css';

export default function App() {
  return (
    <BrowserRouter>
      <ProjectProvider>
        <div className="app-layout">
          <Sidebar />
          <main className="app-main">
            <Routes>
              <Route path="/" element={<PreMeeting />} />
              <Route path="/post-meeting" element={<PostMeeting />} />
              <Route path="/scope-gap" element={<ScopeGap />} />
              <Route path="/user-stories" element={<UserStories />} />
            </Routes>
          </main>
        </div>
      </ProjectProvider>
    </BrowserRouter>
  );
}

