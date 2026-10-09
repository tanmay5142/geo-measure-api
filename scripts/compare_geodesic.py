from pyproj import Geod
from shapely.geometry import Polygon

from app.services.measurement import measure

square = Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98)])

ours = measure(square).value
geodesic = abs(Geod(ellps="WGS84").geometry_area_perimeter(square)[0])

print("UTM area:     ", round(ours, 2))
print("Geodesic area:", round(geodesic, 2))
print("Difference %: ", round(abs(ours - geodesic) / geodesic * 100, 4))
