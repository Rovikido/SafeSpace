import geojson
import math
import asyncio


class Point:
    def __init__(self, x, y) -> None:
        """
        x: Longitude
        y: Latitude
        """
        self.x = x
        self.y = y

    def get(self):
        return (self.x, self.y)
    
    def __str__(self) -> str:
        return f"Point x:{self.x} y:{self.y}"
    
    def __hash__(self) -> int:
        return hash(self.x, self.y)
    

class Segment:
    def __init__(self, points = [Point], resolution = -1) -> None:
        self.points = points
        self.center = self.__get_center()
        self.data = {'pop_count_adj': -1, 'income': -1, 'crime_level': -1}
        self.resolution = -1

    def __get_center(self):
        min_x = min([p.x for p in self.points])
        max_x = max([p.x for p in self.points])
        min_y = min([p.y for p in self.points])
        max_y = max([p.y for p in self.points])
        
        return Point((min_x + max_x)/2, (min_y + max_y)/2)
    
    def point_in_segment(self, point) -> bool:
        polygon = self.get_polygon()
        point_coords = (point.x, point.y)
        
        return polygon.contains(geojson.Point(point_coords))

    def get(self):
        return self.points
    
    def get_raw(self):
        return [pnt.get() for pnt in self.points]

    def get_polygon(self):
        return geojson.Polygon(self.get_raw())
    
    def get_feature(self):
        return geojson.Feature(geometry=self.get_polygon())
    
    async def to_json(self):
        res = {'cords': {'center': {'lon': self.center.x, 'lat': self.center.y}, 
                         'vert': [{'lon': p.x, 'lat': p.y} for p in self.points]},
               'data': self.data,
               'resolution': self.resolution}
        return res
        
    def __hash__(self) -> int:
        return self.center.__hash__()
    

class Grid:
    def __init__(self, seg:Segment) -> None:
        self.points = seg.points
        self.seg = seg
        self.resolution = 0
        self.chunks = []
        self.shape = [0,0]
        self.data_bounds = {'pop_count_adj': None, 'income': None}

    def split_by_res(self, resolution):
        self.resolution = resolution

        min_x = min([p.x for p in self.points])
        max_x = max([p.x for p in self.points])
        min_y = min([p.y for p in self.points])
        max_y = max([p.y for p in self.points])

        num_chunks_x = int((max_x - min_x) / resolution)
        num_chunks_y = int((max_y - min_y) / resolution)
        self.shape = [num_chunks_x, num_chunks_y]
        chunks = []
        for i in range(num_chunks_x):
            for j in range(num_chunks_y):
                chunk_min_x = min_x + i * resolution
                chunk_max_x = chunk_min_x + resolution
                chunk_min_y = min_y + j * resolution
                chunk_max_y = chunk_min_y + resolution

                chunk = Segment([Point(chunk_min_x, chunk_min_y), Point(chunk_max_x, chunk_min_y), 
                         Point(chunk_max_x, chunk_max_y), Point(chunk_min_x, chunk_max_y)], resolution=resolution)
                
                if self.seg.point_in_segment(chunk.center):
                    chunks.append(chunk)

        self.chunks = chunks
        return chunks

    def get_centers(self):
        centers = [c.center for c in self.chunks]
        return centers
    
    def __get_chunk(self, x, y):
        if x < 0 or y < 0 or x >= self.shape[0] or y >= self.shape[1]:
            return None
        return self.chunks[y * self.shape[1] + x]
    
    def __remove_missing_value(self, x, y, value_key, depth=3):
        res = 0
        initial_chunk = self.__get_chunk(x, y)
        weights = [0.5 + math.pow(0.5, depth)] + [math.pow(0.5, p) for p in range(2, depth+1)]
        used_neighbours = {initial_chunk}
        prev_iteration = [initial_chunk]

        for dp in range(depth):
            temp_prev_neighbours = []

            for p in prev_iteration: 
                chunk = self.__get_chunk(p.center.x + 1, p.center.y)
                if chunk and chunk not in used_neighbours and chunk.data[value_key] != -1:
                    temp_prev_neighbours.append(chunk)
                    used_neighbours.add(chunk)

                chunk = self.__get_chunk(p.center.x, p.center.y - 1)
                if chunk and chunk not in used_neighbours and chunk.data[value_key] != -1:
                    temp_prev_neighbours.append(chunk)
                    used_neighbours.add(chunk)

                chunk = self.__get_chunk(p.center.x - 1, p.center.y)
                if chunk and chunk not in used_neighbours and chunk.data[value_key] != -1:
                    temp_prev_neighbours.append(chunk)
                    used_neighbours.add(chunk)

                chunk = self.__get_chunk(p.center.x, p.center.y + 1)
                if chunk and chunk not in used_neighbours and chunk.data[value_key] != -1:
                    temp_prev_neighbours.append(chunk)
                    used_neighbours.add(chunk)

            l_res = [n.data[value_key] for n in temp_prev_neighbours]
            l_res = sum(l_res) / len(l_res) if len(l_res) > 0 else 0
            res += l_res * weights[dp]
            prev_iteration = temp_prev_neighbours

        return res if res > 0 else -1

    def remove_missing_values(self, depth=5):
        for x in range(self.shape[0]):
            for y in range(self.shape[1]):
                chunk = self.__get_chunk(x, y)
                if chunk.data['pop_count_adj'] == -1:
                    self.__remove_missing_value(x, y, 'pop_count_adj', depth=depth-1)
                if chunk.data['income'] <=0:
                    self.__remove_missing_value(x, y, 'income', depth=depth+1)

    def normalize_data(self):
        # constructing bounds
        for val, bound in self.data_bounds.items(): 
            if bound:
                continue
            min_v = min([c.data[val] for c in self.chunks if c.data[val] != -1])
            self.data_bounds[val][0] = min_v if min_v > 0 else 0
            self.data_bounds[val][1] = max([c.data[val] for c in self.chunks if c.data[val] != -1])
        
        # normalizing using bounds
        for c in self.chunks:
            if self.data_bounds['pop_count_adj']:
                c.data['pop_count_adj'] = (c.data['pop_count_adj'] - self.data_bounds['pop_count_adj'][0]) / self.data_bounds['pop_count_adj'][1]
            if self.data_bounds['income']:
                c.data['income'] = (c.data['income'] - self.data_bounds['income'][0]) / self.data_bounds['income'][1]
        
        # reset bounds
        for val, _ in self.data_bounds.items(): 
            self.data_bounds[val] = [0,1]
    
    async def to_json(self):
        loop = asyncio.get_event_loop()
        task_list = []
        for c in self.chunks:
            task_list.append(loop.create_task(c.to_json()))
        res = await asyncio.gather(*task_list)
        return res
        

def create_grid(self, seg:Segment, res_m=1000):
    res = res_m/1000/111
    grid = Grid(seg)
    grid.split_by_res(res)

    return grid