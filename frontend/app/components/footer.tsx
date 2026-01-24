const pages = ['Tournaments', 'Dota', 'Blog'];
const settings = ['Profile', 'Account', 'Dashboard', 'Logout'];

function Footer() {
  return (
    <footer className=" sticky bottom-0 footer sm:footer-horizontal footer-center bg-base-300 text-base-content p-4">
      <aside>
        <p>Copyright © {new Date().getFullYear()} - DraftForge</p>
      </aside>
    </footer>
  );
}
export default Footer;
